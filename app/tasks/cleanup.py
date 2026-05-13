import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete

from app.models.paste import Paste
from app.database import AsyncSessionLocal
from app.config import settings

logger = logging.getLogger("pastevault.cleanup")

BATCH_SIZE = 500


async def purge_expired_pastes() -> int:
    total_deleted = 0
    async with AsyncSessionLocal() as db:
        while True:
            result = await db.execute(
                delete(Paste)
                .where(
                    Paste.expires_at < datetime.now(timezone.utc),
                    Paste.expires_at.isnot(None),
                )
                .limit(BATCH_SIZE)
            )
            await db.commit()
            if result.rowcount == 0:
                break
            total_deleted += result.rowcount
    return total_deleted


async def run_cleanup_loop() -> None:
    interval = settings.CLEANUP_INTERVAL_SECONDS
    while True:
        try:
            deleted = await purge_expired_pastes()
            if deleted:
                logger.info("Purged %d expired paste(s)", deleted)
        except Exception as e:
            logger.error("Cleanup error: %s", e)
        await asyncio.sleep(interval)
