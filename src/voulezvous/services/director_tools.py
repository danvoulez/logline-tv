"""Tools the Director (LLM) may call.

Each tool is a thin wrapper over existing services / routers. They validate
input via a Pydantic schema and return a JSON-serializable dict.

The LLM only chooses which verb to run with which args. It NEVER calls
Python directly. The Director loop validates and dispatches here.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.enums import (
    CandidateRightsStatus,
    DiscoveryStatus,
    KeywordSource,
)
from voulezvous.acquisition.models import (
    CandidateAsset,
    DomainPolicy,
    SearchKeyword,
)
from voulezvous.acquisition.services.bridge import (
    promote_candidate_to_library_asset,
)
from voulezvous.acquisition.workers.discovery import (
    run_discovery,
    run_discovery_simulated,
)
from voulezvous.acquisition.workers.discovery_adult import run_user_discovery
from voulezvous.acquisition.workers.enrichment import run_enrichment
from voulezvous.models.enums import PlanStatus, RightsStatus, StreamItemStatus
from voulezvous.models.tables import LibraryAsset, StreamPlan, StreamPlanItem
from voulezvous.services.planner import generate_plan
from voulezvous.services.stream_control import request_stream_start

logger = structlog.get_logger()

# Acquisition/discovery tools are disabled by default during Phase 4
# Set DIRECTOR_ENABLE_ACQUISITION=true to enable them
DIRECTOR_ENABLE_ACQUISITION = os.environ.get("DIRECTOR_ENABLE_ACQUISITION", "false").lower() == "true"

# Tools that require acquisition/discovery to be enabled
ACQUISITION_TOOLS = {
    "run_discovery",
    "run_user_discovery",
    "run_enrichment",
    "promote_candidate",
}


class ToolError(Exception):
    """Raised when a tool call is invalid or refuses to execute."""


# ── Args schemas (bounded grammar) ────────────────────────────────────────────


class GeneratePlanArgs(BaseModel):
    hours: int = Field(default=24, ge=1, le=48)
    mix_music: bool = False


class NoArgs(BaseModel):
    pass


class RunDiscoveryArgs(BaseModel):
    simulated: bool = False


class RunUserDiscoveryArgs(BaseModel):
    domain: str
    username: str
    max_videos: int = Field(default=20, ge=1, le=100)


class CandidateIdArgs(BaseModel):
    candidate_id: uuid.UUID


class BlockCandidateArgs(BaseModel):
    candidate_id: uuid.UUID
    reason: str = "blocked by director"


class BlockAssetArgs(BaseModel):
    asset_id: uuid.UUID
    reason: str = "blocked by director"


class AddKeywordArgs(BaseModel):
    text: str = Field(min_length=2, max_length=200)
    weight: float = 1.0
    category: str | None = None
    include: bool = True


class KeywordIdArgs(BaseModel):
    keyword_id: uuid.UUID


class BoostKeywordArgs(BaseModel):
    keyword_id: uuid.UUID
    factor: float = Field(default=1.2, ge=0.1, le=5.0)


class DomainIdArgs(BaseModel):
    domain_id: uuid.UUID


# ── Tool implementations ──────────────────────────────────────────────────────


async def tool_generate_plan(db: AsyncSession, args: GeneratePlanArgs) -> dict:
    # Guard rail: if queue already has >= 4h of queued content, refuse.
    # The LLM sometimes hallucinates a low queue. We trust the DB, not the LLM.
    queued_sec = (
        await db.execute(
            select(func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0))
            .join(StreamPlan)
            .where(
                StreamPlan.status.in_(
                    [
                        PlanStatus.approved,
                        PlanStatus.preparing,
                        PlanStatus.ready,
                        PlanStatus.streaming,
                    ]
                )
            )
            .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
        )
    ).scalar_one()
    queued_hours = (int(queued_sec or 0)) / 3600
    if queued_hours >= 4:
        raise ToolError(f"queue already has {queued_hours:.1f}h of content; skipping plan")

    plan = await generate_plan(db, date.today(), hours=args.hours, mix_music=args.mix_music)
    # Auto-approve so prep worker pegs items
    plan.status = PlanStatus.approved
    await db.commit()
    return {
        "plan_id": str(plan.id),
        "items": len(plan.items),
        "hours": args.hours,
        "status": "approved",
    }


async def tool_start_stream(db: AsyncSession, args: NoArgs) -> dict:
    control = await request_stream_start(db)
    return {"desired_running": control.desired_running, "status": control.status}


async def tool_run_discovery(db: AsyncSession, args: RunDiscoveryArgs) -> dict:
    if args.simulated:
        run = await run_discovery_simulated(db)
    else:
        run = await run_discovery(db)
    return {
        "run_id": str(run.id),
        "summary": run.output_summary,
    }


async def tool_run_user_discovery(db: AsyncSession, args: RunUserDiscoveryArgs) -> dict:
    run = await run_user_discovery(db, domain=args.domain, username=args.username, max_videos=args.max_videos)
    return {
        "run_id": str(run.id),
        "domain": args.domain,
        "username": args.username,
        "summary": run.output_summary,
    }


async def tool_run_enrichment(db: AsyncSession, args: NoArgs) -> dict:
    return await run_enrichment(db)


async def tool_promote_candidate(db: AsyncSession, args: CandidateIdArgs) -> dict:
    asset = await promote_candidate_to_library_asset(db, args.candidate_id)
    await db.commit()
    return {
        "candidate_id": str(args.candidate_id),
        "library_asset_id": str(asset.id),
        "title": asset.title,
    }


async def tool_block_candidate(db: AsyncSession, args: BlockCandidateArgs) -> dict:
    c = await db.get(CandidateAsset, args.candidate_id)
    if not c:
        raise ToolError(f"Candidate {args.candidate_id} not found")
    c.rights_status = CandidateRightsStatus.blocked
    c.discovery_status = DiscoveryStatus.rejected
    c.rejection_reason = args.reason
    await db.commit()
    return {"candidate_id": str(c.id), "blocked": True}


async def tool_block_asset(db: AsyncSession, args: BlockAssetArgs) -> dict:
    a = await db.get(LibraryAsset, args.asset_id)
    if not a:
        raise ToolError(f"Asset {args.asset_id} not found")
    a.rights_status = RightsStatus.blocked
    a.approval_notes = args.reason
    await db.commit()
    return {"asset_id": str(a.id), "blocked": True, "reason": args.reason}


async def tool_add_keyword(db: AsyncSession, args: AddKeywordArgs) -> dict:
    existing = (await db.execute(select(SearchKeyword).where(SearchKeyword.keyword == args.text))).scalar_one_or_none()
    if existing:
        # Reactivate if previously paused
        existing.active = True
        existing.weight = args.weight
        if args.category:
            existing.category = args.category
        existing.include = args.include
        await db.commit()
        return {"keyword_id": str(existing.id), "reactivated": True}

    kw = SearchKeyword(
        keyword=args.text,
        weight=args.weight,
        category=args.category,
        include=args.include,
        source=KeywordSource.llm_expanded,
        active=True,
    )
    db.add(kw)
    await db.commit()
    return {"keyword_id": str(kw.id), "created": True}


async def tool_pause_keyword(db: AsyncSession, args: KeywordIdArgs) -> dict:
    kw = await db.get(SearchKeyword, args.keyword_id)
    if not kw:
        raise ToolError(f"Keyword {args.keyword_id} not found")
    kw.active = False
    await db.commit()
    return {"keyword_id": str(kw.id), "paused": True}


async def tool_boost_keyword(db: AsyncSession, args: BoostKeywordArgs) -> dict:
    kw = await db.get(SearchKeyword, args.keyword_id)
    if not kw:
        raise ToolError(f"Keyword {args.keyword_id} not found")
    old = float(kw.weight)
    new = max(0.1, min(old * args.factor, 5.0))
    kw.weight = new
    await db.commit()
    return {"keyword_id": str(kw.id), "old_weight": old, "new_weight": new}


async def tool_disable_domain(db: AsyncSession, args: DomainIdArgs) -> dict:
    policy = await db.get(DomainPolicy, args.domain_id)
    if not policy:
        raise ToolError(f"Domain {args.domain_id} not found")
    policy.is_enabled = False
    await db.commit()
    return {"domain_id": str(policy.id), "disabled": True}


async def tool_narrate(db: AsyncSession, args: BaseModel) -> dict:
    # Pure narration: the line gets stored as the action row in DirectorAction,
    # so this tool only echoes back. The verb itself carries the message.
    return {"narration": True}


class NarrateArgs(BaseModel):
    text: str = Field(min_length=1, max_length=500)


async def tool_run_cleanup(db: AsyncSession, args: NoArgs) -> dict:
    from voulezvous.services.cleanup import run_cleanup_cycle

    return await run_cleanup_cycle(db)


# ── Verb registry ─────────────────────────────────────────────────────────────

TOOLS: dict[str, tuple[type[BaseModel], Any]] = {
    "generate_plan": (GeneratePlanArgs, tool_generate_plan),
    "start_stream": (NoArgs, tool_start_stream),
    "run_discovery": (RunDiscoveryArgs, tool_run_discovery),
    "run_user_discovery": (RunUserDiscoveryArgs, tool_run_user_discovery),
    "run_enrichment": (NoArgs, tool_run_enrichment),
    "promote_candidate": (CandidateIdArgs, tool_promote_candidate),
    "block_candidate": (BlockCandidateArgs, tool_block_candidate),
    "block_asset": (BlockAssetArgs, tool_block_asset),
    "add_keyword": (AddKeywordArgs, tool_add_keyword),
    "pause_keyword": (KeywordIdArgs, tool_pause_keyword),
    "boost_keyword": (BoostKeywordArgs, tool_boost_keyword),
    "disable_domain": (DomainIdArgs, tool_disable_domain),
    "narrate": (NarrateArgs, tool_narrate),
    "run_cleanup": (NoArgs, tool_run_cleanup),
}


def get_tool_grammar_description() -> str:
    """A short, compact description for the LLM prompt."""
    return """
Verbs and required args (strict — extra fields are rejected):

- generate_plan {hours:int=24, mix_music:bool=false} — create + auto-approve a 24h plan
- start_stream {} — set stream desired_running=true
- run_discovery {simulated:bool=false} — full discovery cycle on enabled domains
- run_user_discovery {domain:str, username:str, max_videos:int=20} — scrape a creator
- run_enrichment {} — enrich newly-accepted candidates
- promote_candidate {candidate_id:uuid} — push candidate into library
- block_candidate {candidate_id:uuid, reason:str} — drop a bad candidate
- block_asset {asset_id:uuid, reason:str} — quarantine an asset that keeps failing
- add_keyword {text:str, weight:float=1.0, category:str?, include:bool=true}
- pause_keyword {keyword_id:uuid} — deactivate a keyword
- boost_keyword {keyword_id:uuid, factor:float=1.2} — multiply weight (0.1..5.0)
- disable_domain {domain_id:uuid} — turn a site off
- narrate {text:str} — note for the operator
- run_cleanup {} — delete orphan files in /spool/downloads and /spool/prepared
""".strip()


async def execute_action(db: AsyncSession, verb: str, args_raw: dict) -> tuple[str, dict | None, str | None]:
    """Validate + dispatch a single action.

    Returns (status, result, error). status ∈ {executed, rejected, failed}.
    """
    if verb not in TOOLS:
        return "rejected", None, f"unknown verb: {verb}"

    # Reject acquisition/discovery tools if not enabled
    if verb in ACQUISITION_TOOLS and not DIRECTOR_ENABLE_ACQUISITION:
        return "rejected", None, f"acquisition tool '{verb}' disabled (set DIRECTOR_ENABLE_ACQUISITION=true to enable)"

    schema_cls, func = TOOLS[verb]
    try:
        args = schema_cls.model_validate(args_raw)
    except ValidationError as e:
        return "rejected", None, f"bad args: {e.errors()[:3]}"

    try:
        result = await func(db, args)
        return "executed", result, None
    except ToolError as e:
        return "rejected", None, str(e)
    except Exception as e:
        logger.exception("director.tool_failed", verb=verb)
        return "failed", None, str(e)
