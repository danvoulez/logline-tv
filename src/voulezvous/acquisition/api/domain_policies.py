"""Domain policies API — CRUD for approved websites/domains."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import DomainPolicy
from voulezvous.acquisition.schemas import DomainPolicyCreate, DomainPolicyOut, DomainPolicyUpdate
from voulezvous.database import get_db

router = APIRouter(prefix="/domain-policies", tags=["domain-policies"])


@router.post("", response_model=DomainPolicyOut, status_code=201)
async def create_domain_policy(body: DomainPolicyCreate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(DomainPolicy).where(DomainPolicy.domain == body.domain))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, f"Domain policy for {body.domain} already exists")

    policy = DomainPolicy(**body.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("", response_model=list[DomainPolicyOut])
async def list_domain_policies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DomainPolicy).order_by(DomainPolicy.created_at.desc()))
    return result.scalars().all()


@router.get("/{policy_id}", response_model=DomainPolicyOut)
async def get_domain_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    policy = (await db.execute(select(DomainPolicy).where(DomainPolicy.id == policy_id))).scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Domain policy not found")
    return policy


@router.patch("/{policy_id}", response_model=DomainPolicyOut)
async def update_domain_policy(policy_id: uuid.UUID, body: DomainPolicyUpdate, db: AsyncSession = Depends(get_db)):
    policy = (await db.execute(select(DomainPolicy).where(DomainPolicy.id == policy_id))).scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Domain policy not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)
    return policy


@router.delete("/{policy_id}", status_code=204)
async def delete_domain_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    policy = (await db.execute(select(DomainPolicy).where(DomainPolicy.id == policy_id))).scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Domain policy not found")

    await db.delete(policy)
    await db.commit()
    return None
