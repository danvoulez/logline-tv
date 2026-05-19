# voulezvous.tv — LLM Operator Guide

You control an autonomous 24/7 streaming TV channel via MCP tools.
**Always call `get_tv_status` first.** Never act blind.

---

## System in one paragraph

Content flows through 4 stages: **Candidate → Library → Plan → Stream**.
A Director loop (Ollama, every 5 min) handles this automatically.
Your job: manage inputs (sites + keywords) and unblock jams.

---

## Data pipeline

```
Sites + Keywords
      ↓ run_discovery (every 6h)
CandidateAssets  ← only authorized_direct / authorized_official can be promoted
      ↓ promote_candidate (Director auto-promotes)
LibraryAssets (approved_for_stream)
      ↓ generate_plan (when queue < 4h, requires ≥1 approved video)
StreamPlan → StreamPlanItems (24h schedule)
      ↓ prep-worker (downloads + normalizes, every 30s)
StreamPlanItem.prep_status = ready  ← or failed (no auto-retry)
      ↓ streamer (FFmpeg → HLS)
tv.logline.world  ← DELETE_AFTER_STREAM=true: file deleted after each play
```

---

## Signal states

| `signal` value | Meaning |
|----------------|---------|
| `streaming` | Playing a real video. Good. |
| `fallback` | Playing fallback.mp4. Plan empty, all items failed, or no ready items. |
| `idle` | Stream stopped (`desired_running=false`). Call `force_director_tick`. |
| `no-control-row` | First boot incomplete. Restart API container. |

---

## Key numbers to watch

| Field | Threshold | Action |
|-------|-----------|--------|
| `queued_hours` | < 4h | Director generates plan. If stuck 10+ min, call `generate_plan(24)`. |
| `library.videos_approved` | = 0 | `generate_plan` will fail. Need discovery + promotion first. |
| `heartbeat_stale_sec` | > 180 | Streamer frozen. Director auto-restarts via toggle. |
| `disk.used_pct` | > 85% | Call `run_cleanup()` immediately. |
| `discovery_hours_ago` | > 12 | Call `run_discovery()`. |
| `candidates.approved_unpromoted` | > 0 | Director promotes on next tick. If stuck, `force_director_tick`. |

---

## Candidate retrieval rules (critical)

A candidate can only be promoted if **both** are true:
- `rights_status = approved_for_stream`
- `retrieval_status = authorized_direct` OR `authorized_official`

`metadata_only` candidates **can never be promoted** — we found the video but can't download it. Do not attempt to promote them. Block them to clean the queue.

---

## Health score

Recalculated after every play. Based on last 20 plays:
- `ok` = played ≥80% of planned duration without error
- `health_score = ok_count / min(plays, 20)`

Director auto-blocks assets with `health_score < 0.3` after `error_count ≥ 3`.

---

## Reports

Reports are **not auto-generated**. To generate today's report:
```
POST /reports/2026-05-19/generate
```
Or use the Admin UI → Reports → "Gerar hoje". The Director does not call this automatically.

---

## Tools

### Status
- **`get_tv_status`** — full snapshot. Call this first, always.
- **`get_recent_decisions(limit)`** — last N Director actions with verb/why/status.
- **`force_director_tick`** — make Director evaluate + act right now (up to 5 actions).

### Keywords
- **`list_keywords`** — all keywords with id, weight, include, active.
- **`add_keyword(text, weight, include, category)`** — weight 0.1–5.0. include=False = exclusion filter. Reactivates if keyword already exists.
- **`pause_keyword(keyword_id)`** — deactivate. Pass UUID from `list_keywords`.
- **`boost_keyword(keyword_id, factor)`** — multiply weight by factor (e.g. 1.5 = +50%).

### Sites
- **`list_sites`** — all domains with id, enabled, has_search_template, has_credentials.
- **`disable_site(domain_id)`** — turn off a site. Pass UUID from `list_sites`.

### Content
- **`run_discovery(simulated)`** — scrape all enabled sites. `simulated=True` = dry run, no candidates saved.
- **`generate_plan(hours)`** — force new broadcast plan. Rejected if queue ≥ 4h. Fails if `videos_approved = 0`.
- **`block_asset(asset_id, reason)`** — quarantine a video permanently.

### Maintenance
- **`run_cleanup`** — delete orphan files in `/spool/downloads` and `/spool/prepared`. Use when `disk.used_pct > 85`.
- **`get_stuck_prep_items`** — list items with `prep_status=failed`. These won't auto-retry; block the asset or the plan will never clear.

---

## Decision playbook

**Channel is in FALLBACK:**
1. `get_tv_status` → check `queued_hours` and `library.videos_approved`.
2. `videos_approved = 0` → no content. Run discovery, wait for promotion.
3. `videos_approved > 0`, `queued_hours = 0` → call `generate_plan(24)`.
4. Plan exists, items exist, but `prep_status != ready` → prep-worker is downloading. Check `get_stuck_prep_items`.

**Queue dropping below 4h and Director not acting:**
1. `force_director_tick`.
2. If rejected with "queue already has Xh" → false alarm, queue is fine.

**Discovery hasn't run in > 12h:**
1. `list_sites` — at least one site must be enabled with `has_search_template=true`.
2. `list_keywords` — at least one keyword must be active with `include=true`.
3. Call `run_discovery(false)`.

**Candidates not being promoted:**
1. `get_tv_status` → check `candidates.approved_unpromoted`.
2. If candidates exist but `retrieval_status=metadata_only` → they can never be promoted. Call `block_candidate` to clear them.
3. If `retrieval_status=authorized_direct/official` → `force_director_tick`.

**Disk getting full:**
1. `run_cleanup` first (frees orphan files).
2. If still > 85% → `block_asset` on low-health videos to prevent re-download.
3. Note: `DELETE_AFTER_STREAM=true` means each video is deleted after playing — disk fills from downloads, not archive.

**Prep items stuck failed:**
1. `get_stuck_prep_items` → get asset_ids.
2. If download failed (network, auth) → `block_asset` so the item is skipped and the plan moves on.
3. New plan will replace failed items on next `generate_plan` cycle.

**Bad video keeps failing:**
1. `get_recent_decisions(50)` → find repeated failures.
2. `block_asset(asset_id, "keeps failing")`.

---

## What the Director does automatically (don't duplicate)

- Generates plans when queue < 4h
- Promotes approved candidates (retrieval=authorized_*)
- Runs discovery every 6h
- Restarts streamer if heartbeat stale > 3 min
- Blocks assets with health_score < 0.3 after 3+ plays
- Runs disk cleanup when used_pct > 85%
- Ensures stream is running (`start_stream` on each tick if `running=false`)

Only intervene when the Director has been stuck for > 10 minutes.

---

## What you cannot do via MCP

| Action | Where instead |
|--------|--------------|
| Add a site with credentials | `/admin` UI (passwords never go through MCP) |
| Edit selectors / URL templates | `/admin` UI |
| Generate daily reports | `POST /reports/YYYY-MM-DD/generate` or Admin UI |
| Scrape a specific creator profile | Not exposed (use `/discovery/run-user` REST endpoint) |
| Change stream target URL | `.env` → `STREAM_TARGET` |
| View video content | Not possible |

---

## Auth

```
Authorization: Bearer <token>
```
Server: `https://tv.logline.world/mcp/`
Protocol: MCP Streamable HTTP `2024-11-05`
