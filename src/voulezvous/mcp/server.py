"""MCP server — exposes Director + Keywords + Sites as tools for ChatGPT/any MCP client."""

from __future__ import annotations

import uuid

from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from voulezvous.config import settings
from sqlalchemy import desc, select

from voulezvous.acquisition.models import DomainPolicy, SearchKeyword
from voulezvous.database import async_session
from voulezvous.services.director_state import compact_state
from voulezvous.services.director_tools import (
    AddKeywordArgs,
    BlockAssetArgs,
    BoostKeywordArgs,
    DomainIdArgs,
    GeneratePlanArgs,
    KeywordIdArgs,
    NoArgs,
    RunDiscoveryArgs,
    execute_action,
    tool_add_keyword,
    tool_boost_keyword,
    tool_disable_domain,
    tool_generate_plan,
    tool_pause_keyword,
    tool_run_discovery,
)

mcp = FastMCP(
    name="voulezvous-tv",
    instructions=(
        "You are managing voulezvous.tv, an autonomous 24/7 streaming TV channel. "
        "Use get_tv_status first to understand the current state before taking any action. "
        "The Director loop runs every 5 minutes automatically — only force a tick if something needs immediate attention. "
        "Keywords drive discovery. Sites are where the Director scrapes content."
    ),
)


# ── Status ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_tv_status() -> dict:
    """Full system snapshot: stream signal, queue hours, disk, library counts, last 10 director decisions."""
    async with async_session() as db:
        state = await compact_state(db)
    # Make it readable: flatten what matters
    sig = state["stream"]
    return {
        "signal": sig["status"],
        "running": sig["running"],
        "current_item": (sig["current_item"] or {}).get("title", "—"),
        "queued_hours": sig["queued_hours"],
        "heartbeat_stale_sec": sig["heartbeat_stale_sec"],
        "library": state["library"],
        "candidates": state["candidates"],
        "discovery_hours_ago": state["discovery"]["hours_since_last_run"],
        "disk": state["disk"],
        "last_decisions": state["last_actions"],
    }


@mcp.tool()
async def force_director_tick() -> dict:
    """Force the Director to evaluate the system right now and take up to 5 actions.
    Returns how many actions were executed, rejected, or failed."""
    from voulezvous.services.director import director_tick
    return await director_tick()


@mcp.tool()
async def get_recent_decisions(limit: int = 30) -> list:
    """Last N Director decisions with verb, reason, and status (executed/rejected/failed)."""
    from voulezvous.models.tables import DirectorAction
    async with async_session() as db:
        rows = (
            await db.execute(
                select(DirectorAction).order_by(desc(DirectorAction.created_at)).limit(limit)
            )
        ).scalars().all()
    return [
        {
            "at": str(a.created_at),
            "verb": a.verb,
            "why": a.why,
            "status": a.status,
            "error": a.error,
        }
        for a in rows
    ]


# ── Keywords ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_keywords() -> list:
    """All search keywords with their weight, include/exclude flag, and active status."""
    async with async_session() as db:
        rows = (await db.execute(select(SearchKeyword).order_by(desc(SearchKeyword.weight)))).scalars().all()
    return [
        {
            "id": str(k.id),
            "keyword": k.keyword,
            "weight": float(k.weight),
            "include": k.include,
            "active": k.active,
            "category": k.category,
        }
        for k in rows
    ]


@mcp.tool()
async def add_keyword(
    text: str,
    weight: float = 1.0,
    include: bool = True,
    category: str = "",
) -> dict:
    """Add (or reactivate) a search keyword.
    weight: 0.1–5.0, higher = used more often.
    include=False makes it an exclusion filter.
    """
    async with async_session() as db:
        result = await tool_add_keyword(
            db,
            AddKeywordArgs(
                text=text,
                weight=weight,
                include=include,
                category=category or None,
            ),
        )
    return result


@mcp.tool()
async def pause_keyword(keyword_id: str) -> dict:
    """Pause a keyword so it's no longer used in searches. Pass the keyword UUID."""
    async with async_session() as db:
        result = await tool_pause_keyword(db, KeywordIdArgs(keyword_id=uuid.UUID(keyword_id)))
    return result


@mcp.tool()
async def boost_keyword(keyword_id: str, factor: float = 1.5) -> dict:
    """Multiply a keyword's weight by factor (0.1–5.0). Use to emphasize what's working."""
    async with async_session() as db:
        result = await tool_boost_keyword(db, BoostKeywordArgs(keyword_id=uuid.UUID(keyword_id), factor=factor))
    return result


# ── Sites ─────────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_sites() -> list:
    """All configured scraping sites with their domain, enabled status, and whether credentials are set."""
    async with async_session() as db:
        rows = (await db.execute(select(DomainPolicy))).scalars().all()
    return [
        {
            "id": str(d.id),
            "domain": d.domain,
            "enabled": d.is_enabled,
            "adult": d.is_adult,
            "has_search_template": bool(d.search_url_template),
            "has_credentials": bool(d.credential_email and d.credential_password),
            "requires_login": d.requires_login,
        }
        for d in rows
    ]


@mcp.tool()
async def disable_site(domain_id: str) -> dict:
    """Disable a scraping site by its UUID. Get IDs from list_sites."""
    async with async_session() as db:
        result = await tool_disable_domain(db, DomainIdArgs(domain_id=uuid.UUID(domain_id)))
    return result


# ── Discovery ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def run_discovery(simulated: bool = False) -> dict:
    """Trigger a discovery run across all enabled sites using active keywords.
    simulated=True does a dry run without saving candidates."""
    async with async_session() as db:
        result = await tool_run_discovery(db, RunDiscoveryArgs(simulated=simulated))
    return result


# ── Library ───────────────────────────────────────────────────────────────────


@mcp.tool()
async def block_asset(asset_id: str, reason: str = "blocked via MCP") -> dict:
    """Block a library asset so it's never streamed again. Pass the asset UUID."""
    from voulezvous.services.director_tools import tool_block_asset
    async with async_session() as db:
        result = await tool_block_asset(db, BlockAssetArgs(asset_id=uuid.UUID(asset_id), reason=reason))
    return result


@mcp.tool()
async def generate_plan(hours: int = 24) -> dict:
    """Force a new broadcast plan right now. Only works if queue < 4h."""
    async with async_session() as db:
        result = await tool_generate_plan(db, GeneratePlanArgs(hours=hours))
    return result
