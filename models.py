from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(120), primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_folders_owner_parent_name"),
    )

    id = Column(String(120), primary_key=True, index=True)
    owner_id = Column(String(120), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_id = Column(String(120), ForeignKey("folders.id", ondelete="CASCADE"), index=True, nullable=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", lazy="joined")
    parent = relationship("Folder", remote_side=[id], lazy="joined")


class FileObject(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("owner_id", "folder_id", "name", name="uq_files_owner_folder_name"),
    )

    id = Column(String(120), primary_key=True, index=True)
    owner_id = Column(String(120), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    folder_id = Column(String(120), ForeignKey("folders.id", ondelete="CASCADE"), index=True, nullable=True)

    # original file name
    name = Column(String(255), nullable=False)
    mime_type = Column(String(255), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True)

    # internal storage path (relative to STORAGE_ROOT)
    storage_path = Column(String(1024), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", lazy="joined")
    folder = relationship("Folder", lazy="joined")
