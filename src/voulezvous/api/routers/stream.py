from fastapi import APIRouter

from voulezvous.services.streamer import streamer_state

router = APIRouter(prefix="/stream", tags=["stream"])


@router.post("/start")
async def stream_start():
    if streamer_state.running:
        return {"status": "already_running"}
    streamer_state.request_start()
    return {"status": "start_requested"}


@router.post("/stop")
async def stream_stop():
    streamer_state.request_stop()
    return {"status": "stop_requested"}


@router.get("/status")
async def stream_status():
    return {
        "running": streamer_state.running,
        "current_item_id": str(streamer_state.current_item_id)
        if streamer_state.current_item_id
        else None,
    }


@router.post("/sync-r2")
async def sync_r2():
    from voulezvous.services.r2_upload import sync_hls_dir

    count = await sync_hls_dir()
    return {"uploaded": count}
