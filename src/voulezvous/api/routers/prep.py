from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.database import get_db
from voulezvous.services.prep_worker import run_prep_cycle

router = APIRouter(prefix="/prep", tags=["prep"])


@router.post("/run-once")
async def prep_run_once(db: AsyncSession = Depends(get_db)):
    processed = await run_prep_cycle(db)
    return {"processed": processed}
