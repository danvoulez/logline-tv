"""Keywords API — CRUD for search keywords and exclude terms."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import SearchKeyword
from voulezvous.acquisition.schemas import KeywordCreate, KeywordOut, KeywordUpdate
from voulezvous.database import get_db

router = APIRouter(prefix="/keywords", tags=["keywords"])


@router.post("", response_model=KeywordOut, status_code=201)
async def create_keyword(body: KeywordCreate, db: AsyncSession = Depends(get_db)):
    kw = SearchKeyword(**body.model_dump())
    db.add(kw)
    await db.commit()
    await db.refresh(kw)
    return kw


@router.get("", response_model=list[KeywordOut])
async def list_keywords(
    active_only: bool = False,
    include_only: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SearchKeyword)
    if active_only:
        stmt = stmt.where(SearchKeyword.active.is_(True))
    if include_only is not None:
        stmt = stmt.where(SearchKeyword.include.is_(include_only))
    result = await db.execute(stmt.order_by(SearchKeyword.weight.desc()))
    return result.scalars().all()


@router.patch("/{keyword_id}", response_model=KeywordOut)
async def update_keyword(keyword_id: uuid.UUID, body: KeywordUpdate, db: AsyncSession = Depends(get_db)):
    kw = (await db.execute(select(SearchKeyword).where(SearchKeyword.id == keyword_id))).scalar_one_or_none()
    if not kw:
        raise HTTPException(404, "Keyword not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(kw, field, value)

    await db.commit()
    await db.refresh(kw)
    return kw
