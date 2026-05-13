import redis.asyncio as aioredis
from app.config import settings

redis: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def get_cache(key: str) -> str | None:
    return await redis.get(key)


async def set_cache(key: str, value: str, ttl: int = 300) -> None:
    await redis.setex(key, ttl, value)


async def delete_keys(*keys: str) -> None:
    if keys:
        await redis.delete(*keys)


BURN_ATOMIC_LUA = """
local content = redis.call('GET', KEYS[1])
if not content then
    return nil
end
local views = redis.call('INCR', KEYS[2])
local remaining_ttl = redis.call('TTL', KEYS[1])
if remaining_ttl and remaining_ttl > 0 then
    redis.call('EXPIRE', KEYS[2], remaining_ttl)
end
local burn = redis.call('EXISTS', KEYS[3])
if burn == 1 then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
end
return {content, views, burn}
"""

_burn_atomic_sha: str | None = None


async def burn_read_atomic(short_key: str, views_key: str, burn_key: str) -> tuple | None:
    global _burn_atomic_sha
    if not _burn_atomic_sha:
        _burn_atomic_sha = await redis.script_load(BURN_ATOMIC_LUA)
    try:
        result = await redis.evalsha(_burn_atomic_sha, 3, short_key, views_key, burn_key)
    except redis.exceptions.NoScriptError:
        result = await redis.eval(BURN_ATOMIC_LUA, 3, short_key, views_key, burn_key)
    return result
