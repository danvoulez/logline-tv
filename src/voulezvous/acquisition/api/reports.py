"""Reports API — view autonomy reports."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import AutonomyReport
from voulezvous.acquisition.schemas import AutonomyReportOut
from voulezvous.acquisition.workers.reporter import generate_report
from voulezvous.database import get_db

router = APIRouter(prefix="/reports", tags=["acq-reports"])


@router.get("/{report_date}", response_model=AutonomyReportOut)
async def get_report(report_date: date, db: AsyncSession = Depends(get_db)):
    report = (await db.execute(
        select(AutonomyReport).where(AutonomyReport.report_date == report_date)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, f"No report for {report_date}")
    return report


@router.post("/{report_date}/generate", response_model=AutonomyReportOut, status_code=201)
async def generate_report_endpoint(report_date: date, db: AsyncSession = Depends(get_db)):
    report = await generate_report(db, report_date=report_date)
    return report
