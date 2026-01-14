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
        orm_mode = True


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
        orm_mode = True
        from_attributes=True


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
