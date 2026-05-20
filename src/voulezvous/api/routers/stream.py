from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.database import get_db
from voulezvous.services.stream_control import (
    ReadyBufferBelowThresholdError,
    request_stream_start,
    request_stream_stop,
    stream_status_payload,
)

router = APIRouter(prefix="/stream", tags=["stream"])


@router.post("/start")
async def stream_start(db: AsyncSession = Depends(get_db)):
    try:
        control = await request_stream_start(db)
        return {"status": control.status, "desired_running": control.desired_running}
    except ReadyBufferBelowThresholdError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "rejected",
                "reason": "ready_buffer_below_threshold",
                "ready_buffer_sec": e.ready_buffer_sec,
                "min_ready_buffer_sec": e.min_ready_buffer_sec,
            },
        )


@router.post("/stop")
async def stream_stop(db: AsyncSession = Depends(get_db)):
    control = await request_stream_stop(db)
    return {"status": control.status, "desired_running": control.desired_running}


@router.get("/status")
async def stream_status(db: AsyncSession = Depends(get_db)):
    return await stream_status_payload(db)


@router.post("/sync-r2")
async def sync_r2():
    from voulezvous.services.r2_upload import sync_hls_dir

    count = await sync_hls_dir()
    return {"uploaded": count}
