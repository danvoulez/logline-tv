# voulezvous.tv — LLM Operator Guide

You control an autonomous 24/7 streaming TV channel via MCP tools.
**Always call `get_tv_status` first.** Never act blind.

---

## System in one paragraph

Content flows through 4 stages: **Candidate → Library → Plan → Stream**.
A Director loop (Ollama, every 5 min) handles this automatically.
Your job: manage the inputs (sites + keywords) and unblock jams.

---

## Data pipeline

```
Sites + Keywords
      ↓ run_discovery (every 6h)
CandidateAssets (found on the web)
      ↓ promote_candidate (Director or you)
LibraryAssets (approved_for_stream)
      ↓ generate_plan (when queue < 4h)
StreamPlan → StreamPlanItems (24h schedule)
      ↓ prep-worker (downloads + normalizes files)
StreamPlanItem.prep_status = ready
      ↓ streamer (FFmpeg → HLS)
tv.logline.world
```

---

## Signal states

| `signal` value | Meaning |
|---------------|---------|
| `streaming` | Playing a real video. Good. |
| `fallback` | Playing fallback.mp4 (black screen). Plan empty or all items failed. |
| `idle` | Stream stopped. Call `force_director_tick`. |
| `no-control-row` | DB has no stream_control row. First boot incomplete. |

---

## Key numbers to watch

| Field | Action threshold |
|-------|-----------------|
| `queued_hours` | < 4h → Director generates plan. If stuck, call `generate_plan`. |
| `heartbeat_stale_sec` | > 180 → streamer frozen. Director auto-restarts it. |
| `disk.used_pct` | > 85% → call `run_discovery(simulated=True)` then `force_director_tick` to trigger cleanup. |
| `discovery_hours_ago` | > 12h → call `run_discovery()`. |
| `candidates.approved_unpromoted` | > 0 → Director will promote. If stuck > 10 min, call `force_director_tick`. |

---

## Tools

### Status
- **`get_tv_status`** — full snapshot. Call this first, always.
- **`get_recent_decisions(limit)`** — last N Director actions with verb/why/status.
- **`force_director_tick`** — make Director evaluate + act right now (up to 5 actions).

### Keywords
- **`list_keywords`** — all keywords with id, weight, include, active.
- **`add_keyword(text, weight, include, category)`** — weight 0.1–5.0, include=False = exclusion filter.
- **`pause_keyword(keyword_id)`** — deactivate. Pass UUID from list_keywords.
- **`boost_keyword(keyword_id, factor)`** — multiply weight by factor (e.g. 1.5 = +50%).

### Sites
- **`list_sites`** — all domains with id, enabled, has_search_template, has_credentials.
- **`disable_site(domain_id)`** — turn off a site. Pass UUID from list_sites.

### Content
- **`run_discovery(simulated)`** — scrape all enabled sites with active keywords. simulated=True = dry run.
- **`generate_plan(hours)`** — force new broadcast plan. Rejected if queue already ≥ 4h.
- **`block_asset(asset_id, reason)`** — quarantine a video. Pass UUID from get_tv_status worst assets.

---

## Decision playbook

**Channel is in FALLBACK:**
1. `get_tv_status` → check `queued_hours` and `library.videos_approved`.
2. If `videos_approved` = 0 → no content. Need discovery + promotion first.
3. If `videos_approved` > 0 and `queued_hours` = 0 → call `generate_plan(24)`.
4. If plan exists but items not ready → prep-worker is downloading. Wait or check disk.

**Queue is dropping below 4h and Director isn't acting:**
1. `force_director_tick` → Director should call generate_plan.
2. If rejected with "queue already has Xh" → false alarm, queue is fine.

**Discovery hasn't run in > 12h:**
1. Check `list_sites` — at least one site must be enabled with has_search_template=true.
2. Check `list_keywords` — at least one keyword must be active with include=true.
3. Call `run_discovery(false)`.

**A bad video keeps failing:**
1. `get_tv_status` → check `last_decisions` for block_asset suggestions.
2. `get_recent_decisions(50)` → find asset_id from failed actions.
3. `block_asset(asset_id, "keeps failing")`.

**Keywords not producing results:**
1. `list_keywords` → check active keywords and weights.
2. Pause low-weight irrelevant ones with `pause_keyword`.
3. `add_keyword("better term", weight=2.0)`.
4. `run_discovery()` to test immediately.

---

## What the Director does automatically (don't duplicate)

- Generates plans when queue < 4h
- Promotes approved candidates to library
- Runs discovery every 6h
- Restarts streamer if heartbeat stale > 3 min
- Blocks assets with health_score < 0.3 after 3+ plays
- Runs disk cleanup when used_pct > 85%

Only intervene when the Director has been stuck for > 10 minutes (check `get_recent_decisions` — if last action is old and the problem persists, act).

---

## What you cannot do via MCP

- Add a new site with credentials (use `/admin` UI — passwords never go through MCP)
- Edit selectors or URL templates (use `/admin` UI)
- Approve individual candidates (Director handles this)
- Change stream target URL (`.env` only)
- View video content or thumbnails

---

## Auth

All MCP calls require: `Authorization: Bearer <token>`  
Server: `https://tv.logline.world/mcp/`  
Protocol: MCP Streamable HTTP (2024-11-05)
