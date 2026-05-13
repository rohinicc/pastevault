from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.paste import PasteCreate, PasteOut, PasteRead, PasteMeta, PasswordBody
from app.services.paste_service import (
    create_paste,
    read_paste,
    get_paste_meta,
    delete_paste,
)

router = APIRouter(prefix="/pastes", tags=["PasteVault"])

ERROR_MAP = {
    "BURNED":         (410, "This paste has been burned and is gone forever."),
    "EXPIRED":        (410, "This paste has expired."),
    "NOT_FOUND":      (404, "Paste not found."),
    "WRONG_PASSWORD": (403, "Incorrect password."),
    "INVALID_TOKEN":  (403, "Invalid delete token."),
}


def _raise(e: ValueError) -> NoReturn:
    code, detail = ERROR_MAP.get(str(e), (400, str(e)))
    raise HTTPException(status_code=code, detail=detail)


@router.post("/", response_model=PasteOut, status_code=201)
async def create(payload: PasteCreate, db: AsyncSession = Depends(get_db)):
    if len(payload.content.encode("utf-8")) > 500_000:
        raise HTTPException(413, "Content exceeds 500KB limit")
    return await create_paste(db, payload)


@router.get("/{slug}/meta", response_model=PasteMeta)
async def meta(
    slug: str = Path(..., min_length=4, max_length=12),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_paste_meta(db, slug)
    except ValueError as e:
        _raise(e)


@router.get("/{slug}", response_model=PasteRead)
async def read(
    slug: str = Path(..., min_length=4, max_length=12),
    password: str = Query(default=None, min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await read_paste(db, slug, password)
    except ValueError as e:
        _raise(e)


@router.post("/{slug}/read", response_model=PasteRead)
async def read_with_password(
    slug: str = Path(..., min_length=4, max_length=12),
    body: PasswordBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await read_paste(db, slug, body.password if body else None)
    except ValueError as e:
        _raise(e)


@router.delete("/{slug}", status_code=204)
async def delete(
    slug: str = Path(..., min_length=4, max_length=12),
    token: str = Query(..., min_length=1, description="Delete token returned at creation"),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_paste(db, slug, token)
    except ValueError as e:
        _raise(e)
