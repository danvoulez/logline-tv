---
name: testing-voulezvous
description: End-to-end testing of the Voulezvous streaming engine MVP. Use when verifying API, workers, Docker Compose, or schema changes.
---

# Testing the Voulezvous Streaming Engine

## Prerequisites

- Docker and Docker Compose installed
- No external secrets needed — the app runs with local Postgres via Docker Compose

## Environment Setup

```bash
cd /home/ubuntu/repos/tv-today
cp .env.example .env
docker compose down && docker compose up -d --build
```

Wait for all containers to be healthy:
```bash
docker compose ps
# Expect: db (healthy), api (Up), prep-worker (Up), streamer (Up)
# migrate container exits after running — that's normal
```

## Key Gotchas

- **Enum types**: The SQLAlchemy models use `Enum(..., native_enum=False)` to store enum values as VARCHAR strings. If you see errors like `type "assetkind" does not exist`, it means the models are trying to use native Postgres enums that don't match the migration. Fix: ensure all enum columns in `src/voulezvous/models/tables.py` use `Enum(EnumClass, native_enum=False)`.
- **Prep duration**: A 1-hour plan with 10-second seed clips generates 360 items. Full prep takes ~1 hour. For testing, interrupt after 10-20 items to verify the pipeline works.
- **Seed data**: `docker compose exec api app seed-demo-data` creates 3 approved video assets + 2 pending music assets. Running it multiple times adds duplicates.
- **Migration driver**: Alembic needs `psycopg2-binary` (sync driver) even though the app uses `asyncpg`. Both must be in dependencies.

## Test Sequence

All tests are shell/curl based — no browser recording needed.

### 1. Health Check
```bash
curl -s http://localhost:8000/health
# Expect: {"status":"ok","version":"0.1.0"}
```

### 2. Rights Compliance Gate (Negative Test)
```bash
# Register unapproved asset
curl -s -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -d '{"kind":"video","title":"Test","source_type":"direct_url","source_url":"https://example.com/test.mp4"}'
# Expect: rights_status=pending_review, status=registered

# Try generating plan with no approved assets
curl -s -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date":"2025-06-01","hours":1}'
# Expect: HTTP 500, "No approved video assets available for planning"
```

### 3. Full Lifecycle
```bash
# Seed demo data
docker compose exec api app seed-demo-data

# Verify assets
curl -s http://localhost:8000/assets
# Expect: 3 videos (approved_for_stream/approved), 2 music (pending_review/registered)

# Generate plan
curl -s -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date":"2025-06-01","hours":1}'
# Expect: HTTP 201, status=draft, items non-empty, total target_duration_sec >= 3600

# Approve plan (use plan_id from response)
curl -s -X POST http://localhost:8000/plans/{plan_id}/approve
# Expect: status=approved

# Run prep (may take a long time for many items)
curl -s -X POST http://localhost:8000/prep/run-once
# Expect: processed > 0; check plan items for prep_status=ready

# Generate report
docker compose exec api app reporter --date 2025-06-01
curl -s http://localhost:8000/reports/2025-06-01
# Expect: HTTP 200, status=generated, planned_hours > 0, suggestions non-empty
```

### 4. Asset Approval/Block Auto-Sync
```bash
# Create asset, then approve
curl -s -X PATCH http://localhost:8000/assets/{id} \
  -H "Content-Type: application/json" \
  -d '{"rights_status":"approved_for_stream"}'
# Expect: rights_status=approved_for_stream AND status=approved

# Block the asset
curl -s -X PATCH http://localhost:8000/assets/{id} \
  -H "Content-Type: application/json" \
  -d '{"rights_status":"blocked"}'
# Expect: rights_status=blocked AND status=blocked
```

## Lint & Tests

```bash
pip install -e ".[dev]"
ruff check src/ tests/
pytest -v
# Expect: 10 tests pass
```
