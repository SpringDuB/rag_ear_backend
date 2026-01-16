from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator


class EncryptedPayload(BaseModel):
    payload: str = Field(..., description="RSA encrypted base64 payload")

    @validator("payload")
    def validate_payload(cls, v: str):
        if not v or len(v) < 16:
            raise ValueError("payload is required")
        return v


class AuthPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreate(AuthPayload):
    pass


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class Message(BaseModel):
    message: str


class PublicKeyResponse(BaseModel):
    public_key: str


# ===== Chat =====
class ChatMessage(BaseModel):
    role: str = Field(default="user", description="role: user/assistant/system")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    top_k: int | None = Field(default=3, description="RAG检索TopK，可选")
    model: str | None = None


# ===== File System =====
class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: int | None = Field(default=None, description="父文件夹ID；为空表示根目录")


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255, description="重命名")
    parent_id: int | None = Field(default=None, description="移动到目标父文件夹；为空表示移动到根目录")


class FolderRead(BaseModel):
    id: int
    owner_id: int
    parent_id: int | None
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FileRead(BaseModel):
    id: int
    owner_id: int
    folder_id: int | None
    name: str
    mime_type: str | None = None
    size: int
    sha256: str | None = None
    created_at: datetime
    updated_at: datetime
    storage_path: str | None = None

    class Config:
        from_attributes = True


class FolderChildren(BaseModel):
    folders: list[FolderRead] = Field(default_factory=list)
    files: list[FileRead] = Field(default_factory=list)


class FileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255, description="重命名")
    folder_id: int | None = Field(default=None, description="移动到目标文件夹；为空表示移动到根目录")
