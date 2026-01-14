import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import HTTPException, UploadFile
from openai import AsyncOpenAI
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError
from sse_starlette.sse import EventSourceResponse

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def get_cos_client():
    secret_id = os.environ.get("COS_SECRET_ID")
    secret_key = os.environ.get("COS_SECRET_KEY")
    region = os.environ.get("COS_REGION", "ap-nanjing")
    if not secret_id or not secret_key:
        raise HTTPException(status_code=500, detail="COS 密钥未配置")
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Token=None)
    return CosS3Client(config)


COS_BUCKET = os.environ.get("COS_BUCKET", "extraction-1311618546")
COS_BASE_URL = os.environ.get(
    "COS_BASE_URL",
    f"https://{COS_BUCKET}.cos.{os.environ.get('COS_REGION', 'ap-nanjing')}.myqcloud.com/",
)


async def upload_files_to_cos(upload_files: List[UploadFile]) -> List[Dict[str, Any]]:
    if not upload_files:
        return []

    client = get_cos_client()
    tmp_dir = Path("tmp_uploads")
    tmp_dir.mkdir(exist_ok=True)
    uploaded: List[Dict[str, Any]] = []

    for upload_file in upload_files:
        if not getattr(upload_file, "filename", None):
            continue
        suffix = Path(upload_file.filename).suffix or ""
        union_id = f"{uuid.uuid4()}{suffix}"
        tmp_path = tmp_dir / union_id

        content = await upload_file.read()
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(content)

        try:
            await asyncio.to_thread(
                client.upload_file,
                Bucket=COS_BUCKET,
                Key=union_id,
                LocalFilePath=str(tmp_path),
            )
        except (CosServiceError, CosClientError) as exc:
            raise HTTPException(status_code=500, detail=f"文件上传失败: {str(exc)}")
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass

        file_url = f"{COS_BASE_URL.rstrip('/')}/{union_id}"
        uploaded.append(
            {
                "union_id": union_id,
                "file_url": file_url,
                "original_name": upload_file.filename,
                "content_type": upload_file.content_type,
            }
        )
    return uploaded


def build_message_content(text: str, uploads: Optional[List[Dict[str, Any]]]) -> Any:
    files = uploads or []
    if not files:
        return text

    link_lines = []
    image_parts = []
    for item in files:
        url = item.get("file_url")
        if not url:
            continue
        content_type = (item.get("content_type") or "").lower()
        if content_type.startswith("image/"):
            image_parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            link_lines.append(f"- {item.get('original_name') or '附件'}: {url}")

    link_text = "\n\n附件链接：\n" + "\n".join(link_lines) if link_lines else ""
    if image_parts:
        return [{"type": "text", "text": text + link_text}, *image_parts]
    return text + link_text


def flatten_delta_content(delta: Any) -> str:
    if delta is None:
        return ""
    if isinstance(delta, str):
        return delta
    if isinstance(delta, list):
        parts = []
        for item in delta:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return str(delta)


async def handle_simple_chat(prompt: str, upload_files: List[UploadFile], model: Optional[str] = None, _db=None):
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY 未配置")

    uploaded = await upload_files_to_cos(upload_files)
    user_message = {"role": "user", "content": build_message_content(prompt, uploaded)}

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    completion = await client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": "你是Episcience科研助理，请结合用户提供的信息和附件链接进行简洁、有条理的回复。"},
            user_message,
        ],
        stream=True,
    )

    async def event_gen():
        try:
            async for chunk in completion:
                if len(chunk.choices):
                    delta = chunk.choices[0].delta.content
                    text = flatten_delta_content(delta)
                    if text:
                        payload = {"event": "message", "data": text}
                        yield json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            payload = {"event": "error", "data": str(exc)}
            yield json.dumps(payload, ensure_ascii=False)
        finally:
            payload = {"event": "done", "data": "[DONE]"}
            yield json.dumps(payload, ensure_ascii=False)

    return EventSourceResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
            # "Content-Type": "text/event-stream"
        })
