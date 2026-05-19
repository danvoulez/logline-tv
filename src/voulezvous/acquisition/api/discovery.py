"""Discovery API — trigger and view discovery runs."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import DiscoveryRun
from voulezvous.acquisition.schemas import DiscoveryRunOut
from voulezvous.acquisition.workers.discovery import run_discovery_simulated
from voulezvous.database import get_db

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/run", response_model=DiscoveryRunOut, status_code=201)
async def trigger_discovery(db: AsyncSession = Depends(get_db)):
    run = await run_discovery_simulated(db, run_date=date.today())
    return run


@router.get("/runs", response_model=list[DiscoveryRunOut])
async def list_discovery_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(20)
    )
    return result.scalars().all()
