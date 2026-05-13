import random
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.paste import Paste
from app.redis_client import redis

CHARS = string.ascii_letters + string.digits
SLUG_LENGTH = 8


async def generate_slug(db: AsyncSession) -> str:
    for _ in range(15):
        slug = "".join(random.choices(CHARS, k=SLUG_LENGTH))
        in_redis = await redis.exists(f"paste:short:{slug}")
        if in_redis:
            continue
        in_db = await db.scalar(select(Paste).where(Paste.slug == slug))
        if not in_db:
            return slug
    raise RuntimeError("Slug generation exhausted — try again")
