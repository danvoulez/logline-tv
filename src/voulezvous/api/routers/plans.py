import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.api.schemas import PlanGenerateRequest, PlanOut
from voulezvous.database import get_db
from voulezvous.models.enums import PlanStatus
from voulezvous.models.tables import StreamPlan
from voulezvous.services.planner import generate_plan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/generate", response_model=PlanOut, status_code=201)
async def create_plan(body: PlanGenerateRequest, db: AsyncSession = Depends(get_db)):
    plan = await generate_plan(db, body.plan_date, body.hours, body.mix_music)
    return plan


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    q = select(StreamPlan).where(StreamPlan.id == plan_id).options(selectinload(StreamPlan.items))
    result = await db.execute(q)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.post("/{plan_id}/approve", response_model=PlanOut)
async def approve_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    q = select(StreamPlan).where(StreamPlan.id == plan_id).options(selectinload(StreamPlan.items))
    result = await db.execute(q)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.status != PlanStatus.draft:
        raise HTTPException(400, f"Plan status is {plan.status}, expected draft")
    plan.status = PlanStatus.approved
    await db.commit()
    await db.refresh(plan)
    return plan
