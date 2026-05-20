"""Candidates API — view and manage candidate assets."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.enums import CandidateRightsStatus, RetrievalStatus
from voulezvous.acquisition.models import CandidateAsset
from voulezvous.acquisition.schemas import CandidateOut, CandidateUpdate
from voulezvous.database import get_db

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    rights_status: CandidateRightsStatus | None = None,
    retrieval_status: RetrievalStatus | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CandidateAsset)
    if rights_status:
        stmt = stmt.where(CandidateAsset.rights_status == rights_status)
    if retrieval_status:
        stmt = stmt.where(CandidateAsset.retrieval_status == retrieval_status)
    result = await db.execute(stmt.order_by(CandidateAsset.created_at.desc()).limit(limit))
    return result.scalars().all()


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(CandidateAsset).where(CandidateAsset.id == candidate_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    return c


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(candidate_id: uuid.UUID, body: CandidateUpdate, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(CandidateAsset).where(CandidateAsset.id == candidate_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)

    await db.commit()
    await db.refresh(c)
    return c
