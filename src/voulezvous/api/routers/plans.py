import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.api.schemas import PlanGenerateRequest, PlanOut
from voulezvous.database import get_db
from voulezvous.models.enums import PlanStatus, PrepStatus, StreamItemStatus
from voulezvous.models.tables import StreamPlan, StreamPlanItem
from voulezvous.services.planner import generate_plan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/generate", response_model=PlanOut, status_code=201)
async def create_plan(body: PlanGenerateRequest, db: AsyncSession = Depends(get_db)):
    plan = await generate_plan(db, body.plan_date, body.hours, body.mix_music)
    return plan


@router.get("")
async def list_plans(
    limit: int = Query(30, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List recent plans (no items) with a count summary per status."""
    rows = (
        await db.execute(
            select(StreamPlan).order_by(desc(StreamPlan.created_at)).limit(limit)
        )
    ).scalars().all()

    plan_ids = [r.id for r in rows]
    # Aggregate item counts per plan
    summaries: dict = {}
    if plan_ids:
        agg = (
            await db.execute(
                select(
                    StreamPlanItem.stream_plan_id,
                    func.count(StreamPlanItem.id).label("total"),
                    func.sum(
                        (StreamPlanItem.prep_status == PrepStatus.ready).cast(sa_int_type())
                    ).label("ready"),
                    func.sum(
                        (StreamPlanItem.stream_status == StreamItemStatus.queued).cast(sa_int_type())
                    ).label("queued"),
                    func.sum(
                        (StreamPlanItem.stream_status == StreamItemStatus.completed).cast(sa_int_type())
                    ).label("completed"),
                    func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0).label("dur"),
                ).where(StreamPlanItem.stream_plan_id.in_(plan_ids))
                .group_by(StreamPlanItem.stream_plan_id)
            )
        ).all()
        for row in agg:
            summaries[row[0]] = {
                "items_total": int(row[1] or 0),
                "items_ready": int(row[2] or 0),
                "items_queued": int(row[3] or 0),
                "items_completed": int(row[4] or 0),
                "total_duration_sec": int(row[5] or 0),
            }

    return [
        {
            "id": str(p.id),
            "plan_date": p.plan_date.isoformat() if p.plan_date else None,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "target_start_at": p.target_start_at.isoformat() if p.target_start_at else None,
            "target_end_at": p.target_end_at.isoformat() if p.target_end_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "notes": p.notes,
            **(summaries.get(p.id) or {
                "items_total": 0, "items_ready": 0, "items_queued": 0,
                "items_completed": 0, "total_duration_sec": 0,
            }),
        }
        for p in rows
    ]


def sa_int_type():
    """Cast helper for boolean → int aggregation in Postgres."""
    from sqlalchemy import Integer
    return Integer


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    q = select(StreamPlan).where(StreamPlan.id == plan_id).options(selectinload(StreamPlan.items))
    result = await db.execute(q)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    plan = await db.get(StreamPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    await db.delete(plan)
    await db.commit()
    return None


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
