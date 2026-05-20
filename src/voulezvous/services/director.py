"""The Director — autonomous loop that emits bounded actions.

Every N seconds:
1. Build a compact state snapshot.
2. Ask Ollama (bounded prompt, JSON-only response).
3. Validate + execute up to MAX_ACTIONS verbs.
4. Persist run + each action with status/result/error.

The LLM NEVER writes free prose. It returns JSON in the verb grammar.
If Ollama is unreachable or returns garbage, the loop still tries a
deterministic fallback (generate plan if queue is low) so the channel
keeps moving.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.config import settings
from voulezvous.database import async_session
from voulezvous.logging_config import setup_logging
from voulezvous.models.tables import DirectorAction, DirectorRun
from voulezvous.services.director_state import compact_state
from voulezvous.services.director_tools import (
    GeneratePlanArgs,
    NoArgs,
    execute_action,
    get_tool_grammar_description,
    tool_generate_plan,
    tool_start_stream,
)

logger = structlog.get_logger()

DIRECTOR_INTERVAL_SEC = int(os.environ.get("DIRECTOR_INTERVAL_SEC", "300"))  # 5 min
MAX_ACTIONS_PER_TICK = int(os.environ.get("DIRECTOR_MAX_ACTIONS", "5"))
LLM_TIMEOUT_SEC = int(os.environ.get("DIRECTOR_LLM_TIMEOUT_SEC", "45"))
MIN_QUEUED_HOURS_FALLBACK = float(os.environ.get("DIRECTOR_MIN_QUEUED_HOURS", "4"))


PROMPT_TEMPLATE = """You are the director of voulezvous.tv. You emit JSON actions ONLY.

State:
{state_json}

Available verbs and their args:
{tool_grammar}

Hard rules:
- Output ONLY valid JSON of the form: {{"actions": [{{"verb": "...", "args": {{...}}, "why": "<15 words"}}]}}
- Maximum {max_actions} actions per response.
- If everything is fine (queued_hours >= 4 and no approved-but-unpromoted candidates), return {{"actions": []}}.

Heuristic priorities:
- stream.running is false → start_stream.
- queued_hours < 4 AND library.videos_approved > 0 → generate_plan with hours=24.
- candidates.approved_unpromoted > 0 → promote_candidate for up to 3 ids from candidates.promotable.
- discovery.hours_since_last_run > 6 → run_discovery.
- worst_approved_assets[i].health_score < 0.3 AND error_count >= 3 → block_asset.
- disk.used_pct > 85 → run_cleanup.

Respond now with JSON only.
"""


async def call_ollama(state: dict) -> dict:
    """Call the local LLM and parse its JSON response. Empty on any failure."""
    url = f"{settings.local_llm_url.rstrip('/')}/api/generate"
    prompt = PROMPT_TEMPLATE.format(
        state_json=json.dumps(state, indent=2, default=str),
        tool_grammar=get_tool_grammar_description(),
        max_actions=MAX_ACTIONS_PER_TICK,
    )
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 800},
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = data.get("response", "") or "{}"
        return _parse_llm_json(text)
    except Exception as e:
        logger.warning("director.llm_unavailable", error=str(e))
        return {"actions": [], "_llm_error": str(e)}


def _parse_llm_json(text: str) -> dict:
    """Tolerate code fences and trailing garbage. Always return a dict."""
    if not text:
        return {}
    s = text.strip()
    # strip fences
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # take the first {...} block if there is trailing text
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"actions": parsed}
    except json.JSONDecodeError as e:
        logger.warning("director.llm_json_invalid", error=str(e), text=text[:300])
    return {}


async def _fallback_plan_if_dry(db: AsyncSession, state: dict) -> dict | None:
    """If the LLM gave us nothing useful and the queue is dry, generate a plan
    anyway so the channel does not freeze."""
    queued_hours = (state.get("stream") or {}).get("queued_hours", 0)
    if queued_hours >= MIN_QUEUED_HOURS_FALLBACK:
        return None
    if (state.get("library") or {}).get("videos_approved", 0) == 0:
        return None
    try:
        result = await tool_generate_plan(db, GeneratePlanArgs(hours=24, mix_music=False))
        return result
    except Exception as e:
        logger.warning("director.fallback_plan_failed", error=str(e))
        return None


async def _fallback_ensure_stream(db: AsyncSession, state: dict) -> None:
    stream = state.get("stream") or {}
    if not stream.get("running"):
        try:
            await tool_start_stream(db, NoArgs())
        except Exception as e:
            logger.warning("director.fallback_start_failed", error=str(e))

    # Watchdog: if heartbeat stale > 180s and we want it running, bump it.
    stale = stream.get("heartbeat_stale_sec")
    if stream.get("running") and isinstance(stale, int) and stale > 180:
        try:
            from voulezvous.services.stream_control import (
                get_or_create_stream_control,
            )

            control = await get_or_create_stream_control(db)
            # Toggling desired_running causes the streamer to restart its inner loop
            control.desired_running = False
            await db.commit()
            await asyncio.sleep(0.5)
            control = await get_or_create_stream_control(db)
            control.desired_running = True
            await db.commit()
            logger.warning("director.watchdog_bumped_stream", stale_sec=stale)
        except Exception as e:
            logger.warning("director.watchdog_failed", error=str(e))


async def director_tick() -> dict:
    """One iteration: snapshot → LLM → execute → persist."""
    async with async_session() as db:
        # snapshot first (own transaction)
        snapshot = await compact_state(db)
        await db.commit()

    async with async_session() as db:
        run = DirectorRun(
            started_at=datetime.now(timezone.utc),
            state_snapshot=snapshot,
            llm_response={},
            action_count=0,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    llm = await call_ollama(snapshot)
    actions = llm.get("actions") if isinstance(llm, dict) else None
    if not isinstance(actions, list):
        actions = []

    executed = 0
    rejected = 0
    failed = 0

    async with async_session() as db:
        # Always make sure stream is alive
        await _fallback_ensure_stream(db, snapshot)

        for idx, raw in enumerate(actions[:MAX_ACTIONS_PER_TICK]):
            if not isinstance(raw, dict):
                continue
            verb = str(raw.get("verb", "")).strip()
            args = raw.get("args") or {}
            why = raw.get("why")
            if not isinstance(args, dict):
                args = {}

            status, result, err = await execute_action(db, verb, args)

            action_row = DirectorAction(
                run_id=run_id,
                sequence_index=idx,
                verb=verb or "(empty)",
                args=args,
                why=(str(why)[:500] if why else None),
                status=status,
                result=result,
                error=err,
                executed_at=datetime.now(timezone.utc) if status == "executed" else None,
            )
            db.add(action_row)
            await db.commit()

            if status == "executed":
                executed += 1
            elif status == "rejected":
                rejected += 1
            else:
                failed += 1

        # Deterministic safety net: if LLM proposed nothing but queue is dry,
        # generate a plan anyway.
        if executed == 0:
            fb = await _fallback_plan_if_dry(db, snapshot)
            if fb is not None:
                fb_row = DirectorAction(
                    run_id=run_id,
                    sequence_index=99,
                    verb="generate_plan",
                    args={"hours": 24, "mix_music": False},
                    why="fallback: queue dry, LLM idle",
                    status="executed",
                    result=fb,
                    executed_at=datetime.now(timezone.utc),
                )
                db.add(fb_row)
                await db.commit()
                executed += 1

        run = await db.get(DirectorRun, run_id)
        if run:
            run.finished_at = datetime.now(timezone.utc)
            run.llm_response = llm or {}
            run.action_count = executed + rejected + failed
            await db.commit()

    return {
        "run_id": str(run_id),
        "executed": executed,
        "rejected": rejected,
        "failed": failed,
    }


async def run_director_loop() -> None:
    setup_logging()
    logger.info(
        "director.started",
        interval_sec=DIRECTOR_INTERVAL_SEC,
        max_actions=MAX_ACTIONS_PER_TICK,
        llm_url=settings.local_llm_url,
        model=settings.ollama_model,
    )
    while True:
        try:
            result = await director_tick()
            logger.info("director.tick_done", **result)
        except Exception as e:
            logger.exception("director.tick_failed", error=str(e))
        await asyncio.sleep(DIRECTOR_INTERVAL_SEC)
