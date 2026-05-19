---
name: testing-voulezvous
description: End-to-end testing of the Voulezvous streaming engine MVP. Use when verifying API, workers, Docker Compose, UI, or R2 integration changes.
---

# Testing the Voulezvous Streaming Engine

## Prerequisites

- Docker and Docker Compose installed
- For R2 sync tests: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY`, `CLOUDFLARE_R2_SECRET_KEY` secrets

## Devin Secrets Needed

- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare account ID (org secret)
- `CLOUDFLARE_R2_ACCESS_KEY` — R2 S3-compatible access key with Object Read & Write permission (org secret)
- `CLOUDFLARE_R2_SECRET_KEY` — R2 S3-compatible secret key (org secret)

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

Seed demo data:
```bash
docker compose exec api app seed-demo-data
# Creates: 3 approved videos, 2 pending music assets
```

## Key Gotchas

- **Starlette 1.0 TemplateResponse**: The Docker image may install Starlette 1.0+ which changed `TemplateResponse` signature from `TemplateResponse(name, {"request": request})` to `TemplateResponse(request, name)`. If `/` or `/admin` return 500 errors, check this.
- **Enum types**: The SQLAlchemy models use `Enum(..., native_enum=False)` to store enum values as VARCHAR strings. If you see errors like `type "assetkind" does not exist`, ensure all enum columns use `native_enum=False`.
- **Prep duration**: A 1-hour plan with 10-second seed clips generates 360+ items. Full prep takes a long time. For testing, interrupt after 10-20 items.
- **Seed data**: `seed-demo-data` creates 3 approved videos + 2 pending music. Running it multiple times adds duplicates.
- **R2 credentials in Docker**: The docker-compose.yml does NOT include R2 credentials by default. To test R2 sync, temporarily add `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY`, `CLOUDFLARE_R2_SECRET_KEY`, and `CLOUDFLARE_R2_BUCKET` to the API service environment block, then restart the API container. Revert after testing.
- **Migration driver**: Alembic needs `psycopg2-binary` (sync driver) even though the app uses `asyncpg`.

## Test Sequence — API Tests (Shell/Curl)

### 1. Health Check
```bash
curl -s http://localhost:8000/health
# Expect: {"status":"ok","version":"0.1.0"}
```

### 2. Rights Compliance Gate (Negative Test)
```bash
curl -s -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -d '{"kind":"video","title":"Test","source_type":"direct_url","source_url":"https://example.com/test.mp4"}'
# Expect: rights_status=pending_review, status=registered

curl -s -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date":"2025-06-01","hours":1}'
# Expect: HTTP 500, "No approved video assets available for planning"
```

### 3. Full Lifecycle
```bash
docker compose exec api app seed-demo-data
curl -s http://localhost:8000/assets
# Expect: 3 videos (approved), 2 music (pending)

curl -s -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date":"2025-06-01","hours":1}'
# Expect: HTTP 201, status=draft, items non-empty

curl -s -X POST http://localhost:8000/plans/{plan_id}/approve
# Expect: status=approved
```

### 4. R2 Sync Test
```bash
# Create test HLS file inside the API container
docker compose exec api bash -c 'mkdir -p /spool/hls && echo "#EXTM3U" > /spool/hls/test.m3u8'

# Trigger sync
curl -s -X POST http://localhost:8000/stream/sync-r2
# Expect: {"uploaded":1}

# Verify in R2 (from host, using boto3)
python3 -c "
import boto3, os
c = boto3.client('s3',
    endpoint_url=f'https://{os.environ["CLOUDFLARE_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['CLOUDFLARE_R2_ACCESS_KEY'],
    aws_secret_access_key=os.environ['CLOUDFLARE_R2_SECRET_KEY'],
    region_name='auto')
print(c.list_objects_v2(Bucket='voulezvous-hls', Prefix='hls/test'))"
# Expect: hls/test.m3u8 in Contents
```

### 5. Bumper Plan Verification (API)
```bash
# First create and approve a bumper asset
curl -s -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -d '{"kind":"bumper","title":"Test Bumper","source_type":"direct_url","source_url":"https://example.com/bumper.mp4","duration_sec":5}'
# Approve it
curl -s -X PATCH http://localhost:8000/assets/{bumper_id} \
  -H "Content-Type: application/json" \
  -d '{"rights_status":"approved_for_stream"}'

# Generate plan
curl -s -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date":"2025-06-02","hours":1,"mix_music":true}'
# Expect: Items alternate 10s (video) / 5s (bumper)
# First item (#0) should be video (10s), not bumper
```

## Test Sequence — UI Tests (Browser Recording)

These tests require a screen recording.

### Admin Dashboard (http://localhost:8000/admin)
1. Navigate to `/admin` — verify dashboard loads with stat cards, sidebar, stream status
2. Click "Assets" — verify assets table with Kind/Rights/Status badges
3. Click "+ Add Asset" — fill Kind=Bumper, Title, Source URL, Duration=5 → click Add
4. Verify: yellow BUMPER badge, PENDING rights, toast "Asset created"
5. Click "Approve" on bumper row — verify green APPROVED badge, toast
6. Click "Plans" → "+ Generate Plan" → Date=today, Hours=1, check Mix music → Generate
7. Verify: plan shows alternating 10s/5s items (bumpers inserted between videos)
8. Click "Approve Plan" — verify status → APPROVED, "Run Prep" button appears

### Client Player (http://localhost:8000/)
1. Navigate to `/` — verify:
   - Black background
   - Dark grey video container
   - Centered hot pink (#FF1493) circular play button with glow
   - "VOULEZVOUS" branding in hot pink below video
   - ".TV" sub-branding text
   - "Off air" status indicator with dot
2. Click play button — verify overlay hides, shows "Stream offline — retrying..."

## Lint & Tests

```bash
pip install -e ".[dev]"
ruff check src/ tests/
pytest -v
# Expect: 10 tests pass
```
