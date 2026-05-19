"""Enrichment API — trigger enrichment runs."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.workers.enrichment import run_enrichment
from voulezvous.database import get_db

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


@router.post("/run")
async def trigger_enrichment(db: AsyncSession = Depends(get_db)):
    result = await run_enrichment(db)
    return result
