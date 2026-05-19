from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.api.schemas import ReportOut
from voulezvous.database import get_db
from voulezvous.models.tables import DailyReport

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_date}", response_model=ReportOut)
async def get_report(report_date: date, db: AsyncSession = Depends(get_db)):
    q = select(DailyReport).where(DailyReport.report_date == report_date)
    result = await db.execute(q)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")
    return report
