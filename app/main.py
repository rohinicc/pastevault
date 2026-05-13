import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine
from app.routers import paste
from app.tasks.cleanup import run_cleanup_loop
from app.redis_client import redis as redis_client
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(levelname)s\t%(name)s\t%(message)s",
)
logger = logging.getLogger("pastevault")

_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    _cleanup_task = asyncio.create_task(run_cleanup_loop())
    logger.info("PasteVault started")
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    await engine.dispose()
    await redis_client.close()
    logger.info("PasteVault shut down")


app = FastAPI(
    title="PasteVault",
    description="Encrypted. Ephemeral. Antigravity.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/pastes"):
        ip = request.client.host
        key = f"rate:{ip}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        if count > settings.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    return await call_next(request)


@app.get("/health", tags=["Ops"])
async def health():
    return {"status": "ok", "service": "pastevault"}


app.include_router(paste.router)


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
