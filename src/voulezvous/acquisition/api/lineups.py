"""Lineup API — generate and view lineups."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.acquisition.models import LineupRun
from voulezvous.acquisition.schemas import LineupGenerateRequest, LineupOut
from voulezvous.acquisition.workers.curator import generate_lineup, llm_polish_lineup
from voulezvous.database import get_db

router = APIRouter(prefix="/lineup", tags=["lineup"])


@router.post("/generate", response_model=LineupOut, status_code=201)
async def generate_lineup_endpoint(body: LineupGenerateRequest, db: AsyncSession = Depends(get_db)):
    try:
        lineup = await generate_lineup(
            db,
            lineup_date=body.lineup_date,
            target_hours=body.target_hours,
            mix_music=body.mix_music,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Reload with items
    result = await db.execute(select(LineupRun).where(LineupRun.id == lineup.id).options(selectinload(LineupRun.items)))
    return result.scalar_one()


@router.get("/{lineup_id}", response_model=LineupOut)
async def get_lineup(lineup_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LineupRun).where(LineupRun.id == lineup_id).options(selectinload(LineupRun.items)))
    lineup = result.scalar_one_or_none()
    if not lineup:
        raise HTTPException(404, "Lineup not found")
    return lineup


@router.post("/{lineup_id}/polish")
async def polish_lineup(lineup_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await llm_polish_lineup(db, lineup_id)
    return result
