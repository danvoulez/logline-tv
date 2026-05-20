"""Media IR API — compile and view Media IR jobs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import MediaIRJob
from voulezvous.acquisition.schemas import MediaIRJobOut
from voulezvous.acquisition.workers.media_ir import compile_media_ir
from voulezvous.database import get_db

router = APIRouter(prefix="/media-ir", tags=["media-ir"])


class CompileRequest(BaseModel):
    lineup_id: uuid.UUID


@router.post("/compile")
async def compile_ir(body: CompileRequest, db: AsyncSession = Depends(get_db)):
    result = await compile_media_ir(db, body.lineup_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/jobs", response_model=list[MediaIRJobOut])
async def list_ir_jobs(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MediaIRJob).order_by(MediaIRJob.created_at.desc()).limit(limit))
    return result.scalars().all()
