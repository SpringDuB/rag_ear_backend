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

    # class Config:
    #     env_file = ".env"
    #     env_file_encoding = "utf-8"


settings = Settings()
