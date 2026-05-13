from pydantic import BaseModel, Field, field_validator
from typing import Optional


class PasteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)
    language: str = Field(default="plaintext", max_length=50)
    burn_after_read: bool = False
    ttl_seconds: Optional[int] = Field(
        default=None,
        ge=60,
        le=2_592_000,
        description="None = permanent",
    )
    password: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @field_validator("language")
    @classmethod
    def clean_language(cls, v: str) -> str:
        return v.strip().lower()


class PasteOut(BaseModel):
    slug: str
    url: str
    delete_token: str
    expires_at: Optional[str]
    burn_after_read: bool
    language: str


class PasteRead(BaseModel):
    content: str
    language: str
    burn_after_read: bool
    burned: bool
    view_count: int
    expires_at: Optional[str]


class PasteMeta(BaseModel):
    slug: str
    language: str
    burn_after_read: bool
    is_password_protected: bool
    view_count: int
    expires_at: Optional[str]
    created_at: Optional[str]


class PasswordBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
