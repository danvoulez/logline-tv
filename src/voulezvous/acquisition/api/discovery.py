"""Discovery API — trigger and view discovery runs.

No hardcoded sites here. Endpoints accept any `domain` cadastered in
domain_policies (adult or not).
"""

from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.browser.adapters import get_adapter_for_domain
from voulezvous.acquisition.browser.runtime import BrowserRuntime
from voulezvous.acquisition.models import DiscoveryRun
from voulezvous.acquisition.schemas import DiscoveryRunOut
from voulezvous.acquisition.workers.discovery import run_discovery, run_discovery_simulated
from voulezvous.acquisition.workers.discovery_adult import run_user_discovery
from voulezvous.database import get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/run", response_model=DiscoveryRunOut, status_code=201)
async def trigger_discovery(
    simulated: bool = Query(
        False, description="Use simulated discovery (no browser, for testing)"
    ),
    db: AsyncSession = Depends(get_db),
):
    if simulated:
        run = await run_discovery_simulated(db, run_date=date.today())
    else:
        try:
            run = await run_discovery(db, run_date=date.today())
        except Exception as e:
            logger.warning("real_discovery_failed_falling_back", error=str(e))
            run = await run_discovery_simulated(db, run_date=date.today())
    return run


@router.get("/runs", response_model=list[DiscoveryRunOut])
async def list_discovery_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(20)
    )
    return result.scalars().all()


# ── Domain login / per-user discovery ─────────────────────────────────────────


class DomainLoginRequest(BaseModel):
    domain: str


class DomainLoginResponse(BaseModel):
    domain: str
    success: bool
    message: str


@router.post("/login", response_model=DomainLoginResponse)
async def domain_login(
    req: DomainLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login to ANY cadastered domain and persist the browser session.

    Reads URLs, selectors and credentials from the domain_policies row.
    Session is saved to /spool/browser_profiles/<profile>/ and reused on
    subsequent discovery runs. Operator manages everything via /admin.
    """
    adapter = await get_adapter_for_domain(db, req.domain)
    if adapter is None:
        raise HTTPException(404, f"Domain {req.domain} not registered")

    policy = adapter.policy
    if not policy.login_url:
        raise HTTPException(400, f"Domain {req.domain} has no login_url configured")

    if not policy.credential_email or not policy.credential_password:
        raise HTTPException(
            400,
            f"Credentials missing for {req.domain}. "
            "Set credential_email and credential_password via /admin.",
        )

    runtime = BrowserRuntime()
    try:
        await runtime.launch(profile_name=adapter.session_profile_name)
        result = await runtime.login(
            login_url=adapter.LOGIN_URL,
            email=policy.credential_email,
            password=policy.credential_password,
            email_selector=adapter.LOGIN_EMAIL_SEL,
            pass_selector=adapter.LOGIN_PASS_SEL,
            submit_selector=adapter.LOGIN_SUBMIT_SEL,
            success_check=adapter.LOGIN_SUCCESS_SEL,
        )
    finally:
        await runtime.close()

    if result.get("success"):
        return DomainLoginResponse(
            domain=req.domain,
            success=True,
            message=f"Logged in to {req.domain}. Session: {adapter.session_profile_name}.",
        )
    raise HTTPException(
        status_code=401,
        detail=f"Login failed for {req.domain}: {result.get('error', 'unknown')}",
    )


@router.post("/run-user", response_model=DiscoveryRunOut, status_code=201)
async def trigger_user_discovery(
    domain: str = Query(..., description="Any cadastered domain (e.g. xvideos.com)"),
    username: str = Query(..., description="Creator username / channel slug"),
    max_videos: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Scrape videos from a specific creator/user on a cadastered domain."""
    try:
        run = await run_user_discovery(
            db,
            domain=domain,
            username=username,
            max_videos=max_videos,
            run_date=date.today(),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return run
