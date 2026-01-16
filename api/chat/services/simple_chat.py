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

from utils import DocumentParseError, DocumentParser

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SUPPORTED_DOC_EXTS = {".pdf", ".docx", ".csv", ".xlsx", ".pptx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


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


def build_message_content(
    text: str,
    uploads: Optional[List[Dict[str, Any]]],
    doc_sections: Optional[List[str]] = None,
) -> Any:
    files = uploads or []
    sections = []
    if doc_sections:
        sections.append("\n\n".join(doc_sections))
    if not files:
        if sections:
            return text + "\n\n" + "\n\n".join(sections)
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
    extra_text = "\n\n".join(sections) if sections else ""
    combined = text
    if extra_text:
        combined += "\n\n" + extra_text
    if link_text:
        combined += link_text
    if image_parts:
        return [{"type": "text", "text": combined}, *image_parts]
    return combined


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

    image_files: List[UploadFile] = []
    doc_files: List[UploadFile] = []
    other_files: List[UploadFile] = []
    for upload_file in upload_files or []:
        filename = getattr(upload_file, "filename", "") or ""
        ext = Path(filename).suffix.lower()
        content_type = (upload_file.content_type or "").lower()
        if content_type.startswith("image/") or ext in IMAGE_EXTS:
            image_files.append(upload_file)
        elif ext in SUPPORTED_DOC_EXTS:
            doc_files.append(upload_file)
        else:
            other_files.append(upload_file)

    parser = DocumentParser()
    doc_sections: List[str] = []
    if doc_files:
        tmp_dir = Path("tmp_uploads")
        tmp_dir.mkdir(exist_ok=True)
        for upload_file in doc_files:
            filename = upload_file.filename or "附件"
            suffix = Path(filename).suffix or ""
            tmp_path = tmp_dir / f"{uuid.uuid4()}{suffix}"
            content = await upload_file.read()
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(content)
            try:
                text = parser.parse(tmp_path)
                if text.strip():
                    doc_sections.append(f"[{filename}]\n{text}")
                else:
                    doc_sections.append(f"[{filename}]\n(未提取到内容)")
            except DocumentParseError as exc:
                doc_sections.append(f"[{filename}]\n(解析失败: {exc})")
            except Exception as exc:
                doc_sections.append(f"[{filename}]\n(解析异常: {exc})")
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass

    for upload_file in other_files:
        filename = upload_file.filename or "附件"
        doc_sections.append(f"[{filename}]\n(不支持的文件类型，未解析)")

    uploaded = await upload_files_to_cos(image_files)
    user_message = {"role": "user", "content": build_message_content(prompt, uploaded, doc_sections)}

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
