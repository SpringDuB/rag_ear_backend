import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth
from .api.chat.router import router as chat_router
from .config import settings
from .database import init_db
from .utils.crypto import load_or_create_key_pair

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

allowed_origins = settings.cors_origins
if isinstance(allowed_origins, str):
    allowed_origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat_router)


@app.on_event("startup")
def on_startup():
    init_db()
    load_or_create_key_pair(settings.rsa_private_key_path, settings.rsa_public_key_path)
    logger.info("Episcience API initialized")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
