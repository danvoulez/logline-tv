"""Director API — observe runs/actions and force a tick."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.database import get_db
from voulezvous.models.tables import DirectorAction, DirectorRun

router = APIRouter(prefix="/director", tags=["director"])


@router.get("/runs")
async def list_runs(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DirectorRun).order_by(desc(DirectorRun.started_at)).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "action_count": r.action_count,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(DirectorRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    rows = (
        await db.execute(
            select(DirectorAction)
            .where(DirectorAction.run_id == run_id)
            .order_by(DirectorAction.sequence_index)
        )
    ).scalars().all()
    return {
        "id": str(run.id),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "state_snapshot": run.state_snapshot,
        "llm_response": run.llm_response,
        "action_count": run.action_count,
        "error": run.error,
        "actions": [
            {
                "id": str(a.id),
                "sequence_index": a.sequence_index,
                "verb": a.verb,
                "args": a.args,
                "why": a.why,
                "status": a.status,
                "result": a.result,
                "error": a.error,
                "executed_at": a.executed_at.isoformat() if a.executed_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ],
    }


@router.get("/actions")
async def list_actions(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DirectorAction).order_by(desc(DirectorAction.created_at)).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "run_id": str(a.run_id),
            "verb": a.verb,
            "args": a.args,
            "why": a.why,
            "status": a.status,
            "error": a.error,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.post("/tick")
async def force_tick():
    """Run a director tick now (synchronously)."""
    from voulezvous.services.director import director_tick

    result = await director_tick()
    return result
