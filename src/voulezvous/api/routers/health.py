from fastapi import APIRouter

from voulezvous.api.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health():
    return HealthOut()
