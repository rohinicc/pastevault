import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.paste import Paste
from app.schemas.paste import PasteCreate
from app.redis_client import redis, delete_keys, burn_read_atomic
from app.services.crypto_service import encrypt, decrypt
from app.services.slug_service import generate_slug
from app.config import settings

SHORT_TTL_THRESHOLD = 86_400
REDIS_SHORT_PREFIX = "paste:short:"
REDIS_BURN_PREFIX = "burn:"
REDIS_VIEWS_PREFIX = "views:"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _ensure_views_ttl(slug: str) -> None:
    remaining_ttl = await redis.ttl(f"{REDIS_SHORT_PREFIX}{slug}")
    if remaining_ttl and remaining_ttl > 0:
        await redis.expire(f"{REDIS_VIEWS_PREFIX}{slug}", remaining_ttl)


async def create_paste(db: AsyncSession, payload: PasteCreate) -> dict:
    slug = await generate_slug(db)
    delete_token = str(uuid.uuid4())
    encrypted, password_salt = encrypt(payload.content, payload.password, slug)
    ttl = payload.ttl_seconds

    if ttl and ttl <= SHORT_TTL_THRESHOLD:
        data = json.dumps({
            "encrypted_content": encrypted,
            "language": payload.language,
            "burn_after_read": payload.burn_after_read,
            "is_password_protected": bool(payload.password),
            "password_salt": password_salt,
            "delete_token": _hash_token(delete_token),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl": ttl,
        })
        await redis.setex(f"{REDIS_SHORT_PREFIX}{slug}", ttl, data)
        if payload.burn_after_read:
            await redis.setex(f"{REDIS_BURN_PREFIX}{slug}", ttl, "1")
    else:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl) if ttl else None
        )
        paste = Paste(
            slug=slug,
            encrypted_content=encrypted,
            language=payload.language,
            burn_after_read=payload.burn_after_read,
            is_password_protected=bool(payload.password),
            delete_token_hash=_hash_token(delete_token),
            password_salt=password_salt,
            expires_at=expires_at,
        )
        db.add(paste)
        await db.commit()
        if payload.burn_after_read:
            await redis.set(f"{REDIS_BURN_PREFIX}{slug}", "1")

    expires_at_str = (
        (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        if ttl
        else None
    )
    return {
        "slug": slug,
        "url": f"{settings.BASE_URL}/view.html?slug={slug}",
        "delete_token": delete_token,
        "expires_at": expires_at_str,
        "burn_after_read": payload.burn_after_read,
        "language": payload.language,
    }


async def read_paste(db: AsyncSession, slug: str, password: str | None) -> dict:
    burn_key = f"{REDIS_BURN_PREFIX}{slug}"
    short_key = f"{REDIS_SHORT_PREFIX}{slug}"
    views_key = f"{REDIS_VIEWS_PREFIX}{slug}"

    burn_flag = await redis.exists(burn_key)
    short_exists = await redis.exists(short_key)

    if burn_flag and not short_exists:
        exists_in_db = await db.scalar(select(Paste).where(Paste.slug == slug))
        if not exists_in_db or exists_in_db.is_burned:
            raise ValueError("BURNED")

    result = await burn_read_atomic(short_key, views_key, burn_key)
    if result:
        content_raw, views, was_burned_flag = result
        views = int(views)
        was_burned_flag = bool(was_burned_flag)
        data = json.loads(content_raw)
        content = decrypt(
            data["encrypted_content"],
            password,
            slug,
            data.get("password_salt"),
        )
        return {
            "content": content,
            "language": data["language"],
            "burn_after_read": data["burn_after_read"],
            "burned": was_burned_flag,
            "view_count": views,
            "expires_at": None,
        }

    paste: Paste | None = await db.scalar(
        select(Paste)
        .where(Paste.slug == slug)
        .with_for_update()
    )
    if not paste:
        raise ValueError("NOT_FOUND")
    if paste.is_burned:
        raise ValueError("BURNED")
    if paste.expires_at and paste.expires_at < datetime.now(timezone.utc):
        raise ValueError("EXPIRED")

    content = decrypt(paste.encrypted_content, password, slug, paste.password_salt)

    language = paste.language
    burn_after_read = paste.burn_after_read
    view_count = paste.view_count + 1
    expires_at = paste.expires_at.isoformat() if paste.expires_at else None
    burned = False

    paste.view_count = view_count

    if burn_after_read:
        paste.is_burned = True
        burned = True
        await delete_keys(burn_key)

    await db.commit()

    return {
        "content": content,
        "language": language,
        "burn_after_read": burn_after_read,
        "burned": burned,
        "view_count": view_count,
        "expires_at": expires_at,
    }


async def get_paste_meta(db: AsyncSession, slug: str) -> dict:
    raw = await redis.get(f"{REDIS_SHORT_PREFIX}{slug}")
    if raw:
        data = json.loads(raw)
        ttl = await redis.ttl(f"{REDIS_SHORT_PREFIX}{slug}")
        views = await redis.get(f"{REDIS_VIEWS_PREFIX}{slug}") or "0"
        return {
            "slug": slug,
            "language": data["language"],
            "burn_after_read": data["burn_after_read"],
            "is_password_protected": data["is_password_protected"],
            "view_count": int(views),
            "expires_at": f"~{ttl}s remaining",
            "created_at": data.get("created_at"),
        }

    paste: Paste | None = await db.scalar(select(Paste).where(Paste.slug == slug))
    if not paste or paste.is_burned:
        raise ValueError("NOT_FOUND")

    return {
        "slug": paste.slug,
        "language": paste.language,
        "burn_after_read": paste.burn_after_read,
        "is_password_protected": paste.is_password_protected,
        "view_count": paste.view_count,
        "expires_at": paste.expires_at.isoformat() if paste.expires_at else None,
        "created_at": paste.created_at.isoformat() if paste.created_at else None,
    }


async def delete_paste(db: AsyncSession, slug: str, token: str) -> None:
    short_key = f"{REDIS_SHORT_PREFIX}{slug}"
    token_hash = _hash_token(token)

    raw = await redis.get(short_key)
    if raw:
        data = json.loads(raw)
        if data["delete_token"] != token_hash:
            raise ValueError("INVALID_TOKEN")
        await delete_keys(
            short_key,
            f"{REDIS_BURN_PREFIX}{slug}",
            f"{REDIS_VIEWS_PREFIX}{slug}",
        )
        return

    paste: Paste | None = await db.scalar(select(Paste).where(Paste.slug == slug))
    if not paste:
        raise ValueError("NOT_FOUND")
    if paste.delete_token_hash != token_hash:
        raise ValueError("INVALID_TOKEN")

    await db.delete(paste)
    await db.commit()
    await delete_keys(
        f"{REDIS_BURN_PREFIX}{slug}",
        f"{REDIS_VIEWS_PREFIX}{slug}",
    )
