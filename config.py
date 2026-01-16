from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Episcience API"
    secret_key: str = Field("change-me", env="SECRET_KEY")
    access_token_expire_minutes: int = Field(60 * 24, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    database_url: str = Field(
        "mysql+pymysql://root:roottest@localhost:3306/rag_ear",
        env="DATABASE_URL",
    )
    rsa_private_key_path: Path = Field(Path("backend/keys/private.pem"), env="RSA_PRIVATE_KEY_PATH")
    rsa_public_key_path: Path = Field(Path("backend/keys/public.pem"), env="RSA_PUBLIC_KEY_PATH")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], env="CORS_ORIGINS")
    storage_root: Path = Field(Path("backend/storage"), env="STORAGE_ROOT")

    openai_api_key: str = Field("none", env="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com", env="OPENAI_BASE_URL")
    aihub_api_key: str = Field("none", env="AIHUB_API_KEY")
    aihub_base_url: str = Field("https://aihubmix.com/v1", env="AIHUB_BASE_URL")

    cos_bucket: str = Field("none", env="COS_BUCKET")
    cos_secret_id: str = Field("none", env="COS_SECRET_ID")
    cos_secret_key: str = Field("none", env="COS_SECRET_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
