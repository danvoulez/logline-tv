import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.api.schemas import AssetCreate, AssetOut, AssetUpdate
from voulezvous.database import get_db
from voulezvous.models.enums import AssetKind, AssetStatus, RightsStatus
from voulezvous.models.tables import LibraryAsset

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=AssetOut, status_code=201)
async def create_asset(body: AssetCreate, db: AsyncSession = Depends(get_db)):
    asset = LibraryAsset(
        kind=body.kind,
        title=body.title,
        source_type=body.source_type,
        source_url=body.source_url,
        local_source_path=body.local_source_path,
        source_name=body.source_name,
        duration_sec=body.duration_sec,
        tags=body.tags,
        notes=body.notes,
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
async def list_assets(
    kind: AssetKind | None = None,
    rights_status: RightsStatus | None = None,
    status: AssetStatus | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(LibraryAsset)
    if kind is not None:
        q = q.where(LibraryAsset.kind == kind)
    if rights_status is not None:
        q = q.where(LibraryAsset.rights_status == rights_status)
    if status is not None:
        q = q.where(LibraryAsset.status == status)
    q = q.order_by(LibraryAsset.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    asset = await db.get(LibraryAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    return asset


@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: uuid.UUID, body: AssetUpdate, db: AsyncSession = Depends(get_db)
):
    asset = await db.get(LibraryAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    update_data = body.model_dump(exclude_unset=True)

    if "rights_status" in update_data:
        new_rights = update_data["rights_status"]
        if new_rights == RightsStatus.approved_for_stream:
            update_data["status"] = AssetStatus.approved
        elif new_rights == RightsStatus.blocked:
            update_data["status"] = AssetStatus.blocked

    for key, value in update_data.items():
        setattr(asset, key, value)

    await db.commit()
    await db.refresh(asset)
    return asset
