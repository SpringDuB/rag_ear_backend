from datetime import datetime, timedelta
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import uuid

from config import settings
from database import get_db
from models import User
from schemas import EncryptedPayload, Message, PublicKeyResponse, TokenResponse, UserRead
from utils.crypto import decrypt_payload, export_public_key_pem, load_or_create_key_pair

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
token_scheme = HTTPBearer()

_private_key = None
_public_key = None


def get_keys() -> Tuple:
    global _private_key, _public_key
    if _private_key and _public_key:
        return _private_key, _public_key
    _private_key, _public_key = load_or_create_key_pair(settings.rsa_private_key_path, settings.rsa_public_key_path)
    return _private_key, _public_key


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(token_scheme), db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        sub = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return user


@router.get("/public-key", response_model=PublicKeyResponse)
def fetch_public_key():
    _, public_key = get_keys()
    return PublicKeyResponse(public_key=export_public_key_pem(public_key))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: EncryptedPayload, db: Session = Depends(get_db)):
    private_key, _ = get_keys()
    try:
        decrypted = decrypt_payload(payload.payload, private_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法解密请求数据") from exc

    username = decrypted.get("username")
    password = decrypted.get("password")
    email = decrypted.get("email")
    full_name = decrypted.get("full_name")

    if not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名和密码不能为空")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被注册")

    if email:
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册")

    user_id = uuid.uuid4().hex.replace('-', '')
    user = User(
        id=user_id,
        username=username,
        email=email,
        full_name=full_name,
        password_hash=get_password_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRead.from_orm(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: EncryptedPayload, db: Session = Depends(get_db)):
    private_key, _ = get_keys()
    try:
        decrypted = decrypt_payload(payload.payload, private_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法解密请求数据") from exc

    username = decrypted.get("username")
    password = decrypted.get("password")

    if not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名和密码不能为空")

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户已被禁用")

    token = create_access_token({"sub": f"{user.id}"})
    return TokenResponse(access_token=token, user=UserRead.from_orm(user))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return UserRead.from_orm(current_user)


@router.post("/logout", response_model=Message)
def logout():
    return Message(message="客户端请删除本地凭证即可完成退出登录")
