import hashlib
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import FileObject, Folder, User
from schemas import FileRead, FileUpdate, FolderChildren, FolderCreate, FolderRead, FolderUpdate
from api.auth import get_current_user
from config import settings
from database import get_db
from models import FileObject, Folder, User
from schemas import FileRead, FileUpdate, FolderChildren, FolderCreate, FolderRead, FolderUpdate
from api.auth import get_current_user

router = APIRouter(prefix="/api/fs", tags=["FileSystem"])


def _ensure_storage_root() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _folder_path_parts(db: Session, owner_id: int, folder_id: Optional[int]) -> list[str]:
    # Build safe path parts: /<owner_id>/<folder_id-chain>/  (no user-controlled names)
    parts = [str(owner_id)]
    if folder_id is None:
        return parts

    seen: set[int] = set()
    cur = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == owner_id).first()
    if not cur:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")

    chain: list[int] = []
    while cur is not None:
        if cur.id in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹结构异常")
        seen.add(cur.id)
        chain.append(cur.id)
        if cur.parent_id is None:
            break
        cur = db.query(Folder).filter(Folder.id == cur.parent_id, Folder.owner_id == owner_id).first()
    chain.reverse()
    parts.extend([str(x) for x in chain])
    return parts


def _get_folder_owned(db: Session, owner_id: int, folder_id: int) -> Folder:
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == owner_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    return folder


def _get_file_owned(db: Session, file_id: int) -> FileObject:
    obj = db.query(FileObject).filter(FileObject.id == file_id).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return obj


def _assert_folder_move_ok(db: Session, owner_id: int, folder_id: int, new_parent_id: Optional[int]) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == folder_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移动到自身")

    # Ensure new_parent exists and not in folder's descendants
    cur = _get_folder_owned(db, owner_id, new_parent_id)
    seen: set[int] = set()
    while cur is not None and cur.parent_id is not None:
        if cur.id in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹结构异常")
        seen.add(cur.id)
        if cur.parent_id == folder_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移动到子文件夹内")
        cur = db.query(Folder).filter(Folder.id == cur.parent_id, Folder.owner_id == owner_id).first()


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        # ignore disk deletion errors to avoid blocking DB cleanup
        pass


def _delete_folder_recursive(db: Session, owner_id: int, folder_id: int) -> int:
    """
    Recursively delete a folder and all its descendants (folders + files).
    Returns number of deleted DB rows (approx).
    """
    deleted = 0

    # delete files in this folder
    files = db.query(FileObject).filter(FileObject.owner_id == owner_id, FileObject.folder_id == folder_id).all()
    for f in files:
        abs_path = (Path(settings.storage_root) / f.storage_path).resolve()
        _safe_unlink(abs_path)
        db.delete(f)
        deleted += 1

    # recurse into subfolders
    subfolders = db.query(Folder).filter(Folder.owner_id == owner_id, Folder.parent_id == folder_id).all()
    for sf in subfolders:
        deleted += _delete_folder_recursive(db, owner_id, sf.id)

    folder = _get_folder_owned(db, owner_id, folder_id)
    db.delete(folder)
    deleted += 1
    return deleted


@router.post("/folders", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parent_id = body.parent_id
    if parent_id is not None:
        parent = db.query(Folder).filter(Folder.id == parent_id, Folder.owner_id == current_user.id).first()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父文件夹不存在")

    folder = Folder(owner_id=current_user.id, parent_id=parent_id, name=body.name)
    db.add(folder)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同级目录下已存在同名文件夹")
    db.refresh(folder)
    return FolderRead.from_orm(folder)


@router.get("/folders/{folder_id}", response_model=FolderRead)
def get_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user.id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    return FolderRead.from_orm(folder)


@router.patch("/folders/{folder_id}", response_model=FolderRead)
def update_folder(
    folder_id: str,
    body: FolderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = _get_folder_owned(db, current_user.id, folder_id)

    # move
    if body.parent_id is not None or body.parent_id is None:
        # Note: parent_id is optional but explicit null means move to root; Pydantic can't distinguish
        # missing vs null easily here, but for our use we accept both: if provided set, else ignore.
        pass

    if "parent_id" in body.model_fields_set:
        new_parent_id = body.parent_id
        if new_parent_id is not None:
            _get_folder_owned(db, current_user.id, new_parent_id)
        _assert_folder_move_ok(db, current_user.id, folder_id, new_parent_id)
        folder.parent_id = new_parent_id

    # rename
    if body.name is not None:
        folder.name = body.name

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同级目录下已存在同名文件夹")
    db.refresh(folder)
    return FolderRead.from_orm(folder)


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # recursive cleanup to avoid relying on DB cascade settings
    _ensure_storage_root()
    try:
        deleted = _delete_folder_recursive(db, current_user.id, folder_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除失败") from exc
    return {"deleted": deleted}


@router.get("/folders/{folder_id}/children", response_model=FolderChildren)
def list_children(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user.id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")

    folders = (
        db.query(Folder)
        .filter(Folder.owner_id == current_user.id, Folder.parent_id == folder_id)
        .order_by(Folder.created_at.desc())
        .all()
    )
    files = (
        db.query(FileObject)
        .filter(FileObject.owner_id == current_user.id, FileObject.folder_id == folder_id)
        .order_by(FileObject.created_at.desc())
        .all()
    )
    return FolderChildren(
        folders=[FolderRead.from_orm(x) for x in folders],
        files=[FileRead.from_orm(x) for x in files],
    )


@router.get("/root/children", response_model=FolderChildren)
def list_root_children(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folders = (
        db.query(Folder)
        .filter(Folder.owner_id == current_user.id, Folder.parent_id.is_(None))
        .order_by(Folder.created_at.desc())
        .all()
    )
    files = (
        db.query(FileObject)
        .filter(FileObject.owner_id == current_user.id, FileObject.folder_id.is_(None))
        .order_by(FileObject.created_at.desc())
        .all()
    )
    return FolderChildren(
        folders=[FolderRead.from_orm(x) for x in folders],
        files=[FileRead.from_orm(x) for x in files],
    )


@router.post("/files", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    folder_id: str | None = Form(default=None, description="目标文件夹ID；为空表示根目录"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_storage_root()
    parts = _folder_path_parts(db, current_user.id, folder_id)
    file_id = uuid.uuid4().hex.replace('-', '')
    # store as: <STORAGE_ROOT>/<owner>/<folder-chain>/<uuid>
    storage_rel_dir = Path(*parts)
    storage_dir = Path(settings.storage_root) / storage_rel_dir
    storage_dir.mkdir(parents=True, exist_ok=True)

    storage_name = uuid.uuid4().hex
    storage_rel_path = (storage_rel_dir / storage_name).as_posix()
    storage_abs_path = (Path(settings.storage_root) / storage_rel_dir / storage_name).resolve()

    hasher = hashlib.sha256()
    size = 0

    try:
        async with aiofiles.open(storage_abs_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                hasher.update(chunk)
                await f.write(chunk)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="保存文件失败") from exc
    finally:
        await file.close()

    obj = FileObject(
        id=file_id,
        owner_id=current_user.id,
        folder_id=folder_id,
        name=file.filename or "unnamed",
        mime_type=file.content_type,
        size=size,
        sha256=hasher.hexdigest(),
        storage_path=storage_rel_path,
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # allow same file name? currently unique constraint; if conflict, return 409
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同一目录下已存在同名文件")
    db.refresh(obj)
    return FileRead.from_orm(obj)


@router.get("/files/{file_id}", response_model=FileRead)
def get_file_meta(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = _get_file_owned(db, file_id)
    return FileRead.from_orm(obj)


@router.patch("/files/{file_id}", response_model=FileRead)
def update_file(
    file_id: str,
    body: FileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = _get_file_owned(db, current_user.id, file_id)

    # move
    if "folder_id" in body.model_fields_set:
        new_folder_id = body.folder_id
        if new_folder_id is not None:
            _get_folder_owned(db, current_user.id, new_folder_id)
        obj.folder_id = new_folder_id

    # rename
    if body.name is not None:
        obj.name = body.name

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同一目录下已存在同名文件")
    db.refresh(obj)
    return FileRead.from_orm(obj)


@router.delete("/files/{file_id}")
def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_storage_root()
    obj = _get_file_owned(db, current_user.id, file_id)
    abs_path = (Path(settings.storage_root) / obj.storage_path).resolve()
    _safe_unlink(abs_path)
    db.delete(obj)
    db.commit()
    return {"deleted": 1}


@router.get("/files/{file_id}/download")
def download_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = _get_file_owned(db, current_user.id, file_id)

    abs_path = (Path(settings.storage_root) / obj.storage_path).resolve()
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件内容不存在")

    return FileResponse(
        path=str(abs_path),
        media_type=obj.mime_type or "application/octet-stream",
        filename=obj.name,
    )
@router.get("/files/download/{id}")
def download_file2(
    id: str,
    db: Session = Depends(get_db)
):
    obj = db.query(FileObject).filter(FileObject.id == id).first()

    abs_path = (Path(settings.storage_root) / obj.storage_path).resolve()
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件内容不存在")

    return FileResponse(
        path=str(abs_path),
        media_type=obj.mime_type or "application/octet-stream",
        filename=obj.name,

    )




@router.get("/files/download/{name}")
def download_file3(
    filename: str,
    db: Session = Depends(get_db)
):
    obj = db.query(FileObject).filter(FileObject.name == filename).first()

    abs_path = (Path(settings.storage_root) / obj.storage_path).resolve()
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件内容不存在")

    return FileResponse(
        path=str(abs_path),
        media_type=obj.mime_type or "application/octet-stream",
        filename=obj.name,
        headers={"Content-Disposition": f'attachment; filename="{obj.name}"'},
    )
