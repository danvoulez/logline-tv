# Voulezvous — Autonomous Acquisition & Curation Subsystem

## Architecture

Three compilers + one orchestrator:

```
keywords + domains + browser sessions + yesterday report
  → Discovery Compiler (browser runtime → candidates)
  → Curation Compiler (deterministic lineup → LLM polish)
  → Media Compiler (IR objects → prep pipeline handoff)
  → Autonomous Orchestrator (daily cycle)
```

## Components

| Component | CLI Command | API Endpoint |
|-----------|-------------|--------------|
| Domain Policies | — | `POST/GET/PATCH /domain-policies` |
| Keywords | — | `POST/GET/PATCH /keywords` |
| Discovery Worker | `app discovery-worker run` | `POST /discovery/run` |
| Enrichment Worker | `app enrichment-worker run` | `POST /enrichment/run` |
| Curator Planner | `app curator-planner generate --date YYYY-MM-DD` | `POST /lineup/generate` |
| Media IR Compiler | `app media-ir-compiler run --lineup-id UUID` | `POST /media-ir/compile` |
| Reporter | `app acq-reporter generate --date YYYY-MM-DD` | `GET /acq/reports/{date}` |
| Orchestrator | `app orchestrator run-daily` | — |
| Seed Data | `app seed-acquisition-data` | — |

## Quick Start

```bash
# Start infrastructure
docker compose up -d db
docker compose run --rm migrate

# Seed acquisition demo data
docker compose exec api app seed-acquisition-data

# Run the full autonomous daily cycle
docker compose exec api app orchestrator run-daily

# Or run steps individually:
docker compose exec api app discovery-worker run
docker compose exec api app enrichment-worker run
docker compose exec api app curator-planner generate --date 2026-05-19
docker compose exec api app media-ir-compiler run --lineup-id <UUID>
docker compose exec api app acq-reporter generate --date 2026-05-19
```

## Safety Boundaries

1. **Local models only** — No cloud LLM. Uses Ollama (llama3.2) or deterministic fallback.
2. **Authorized websites only** — Only operator-approved domains via `domain_policies`.
3. **Authorized retrieval only** — Only `direct_url`, `official_download`, `official_api`, `uploaded_file`. No DRM bypass, no scraping tricks.
4. **LLM has no sovereign execution** — Browser runtime executes; LLM proposes bounded tool calls only.
5. **Fail closed** — On ambiguity or policy violation, mark `blocked`/`metadata_only`.

## Database Schema (10 tables)

1. `domain_policies` — approved domains + configuration
2. `search_keywords` — include/exclude keywords with weights
3. `discovery_runs` — discovery execution records
4. `candidate_assets` — discovered content with metadata
5. `retrieval_adapters` — authorized download methods
6. `asset_enrichments` — soft metadata (mood, energy, fitness)
7. `lineup_runs` — 24h lineup generations
8. `lineup_items` — individual scheduled slots
9. `media_ir_jobs` — compiled Media IR (no raw ffmpeg)
10. `autonomy_reports` — daily operational reports

## Bounded Tool Grammar

The LLM can only emit these 16 typed verbs:

`search_site`, `open_result`, `inspect_candidate`, `verify_playback`,
`extract_metadata`, `register_retrieval_adapter`, `reject_candidate`,
`expand_keywords`, `enrich_candidate`, `build_candidate_shelf`,
`rerank_candidates`, `schedule_slot`, `insert_buffer`,
`choose_music_pairing`, `emit_media_ir`, `write_report`

Each verb has typed request/response schemas and audit logging.

## Media IR

The system produces compact IR objects — never raw ffmpeg commands:

```json
{
  "asset_id": "uuid",
  "ops": [
    { "op": "trim", "start_sec": 0, "end_sec": 1800 },
    { "op": "normalize_audio", "target_lufs": -14.0 },
    { "op": "underlay_music", "music_ref": "ambient_chill", "video_gain": 0.5, "music_gain": 0.5 },
    { "op": "fade_in", "duration_sec": 1.5 },
    { "op": "fade_out", "duration_sec": 2.0 },
    { "op": "export_profile", "profile": "broadcast_standard" }
  ]
}
```

## Report-Driven Autonomy

Yesterday's report adjusts today's run:
- Boost/reduce keyword weights based on effectiveness
- Deprioritize failing domains
- Surface operator suggestions only when truly needed
