from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, Index
from sqlalchemy.sql import func
from app.database import Base


class Paste(Base):
    __tablename__ = "pastes"

    slug                  = Column(String(12), primary_key=True, index=True)
    encrypted_content     = Column(Text, nullable=False)
    language              = Column(String(50), default="plaintext", nullable=False)
    burn_after_read       = Column(Boolean, default=False, nullable=False)
    is_password_protected = Column(Boolean, default=False, nullable=False)
    delete_token_hash     = Column(String(64), nullable=False)
    password_salt         = Column(String(64), nullable=True)
    view_count            = Column(Integer, default=0, nullable=False)
    expires_at            = Column(DateTime(timezone=True), nullable=True)
    is_burned             = Column(Boolean, default=False, nullable=False)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_pastes_expires_at", "expires_at"),
        Index("ix_pastes_is_burned", "is_burned"),
    )
