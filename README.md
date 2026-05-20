# Voulezvous Streaming Engine

Curated, planned, non-realtime broadcasting backend for **voulezvous.tv**.

## Architecture

```
Library → Plan → Prepare → Stream → Log → Delete local bytes → Daily report
```

One codebase, separate runnable modes:

| Mode | Purpose |
|------|---------|
| `api` | FastAPI operator API (port 8000) |
| `planner` | Generate stream plans from approved assets |
| `prep-worker` | Download, normalize, mix → produce ready-to-play files |
| `streamer` | Play prepared files to RTMP target or test sink |
| `reporter` | Generate daily summary reports |
| `seed-demo-data` | Load demo assets |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.12+ for local dev

### 1. Clone & configure

```bash
git clone https://github.com/danvoulez/tv-today.git
cd tv-today
cp .env.example .env
```

### 2. Start core streaming stack

```bash
docker compose up -d --build
```

This starts: Postgres, runs migrations, API server, prep-worker, and streamer.

### 2.1. Start autonomous Director (optional)

```bash
docker compose --profile director up -d director
```

This starts the LLM-bounded autonomous Director for plan generation and curation.

### 3. Seed demo data

```bash
docker compose exec api app seed-demo-data
```

### 4. Verify

```bash
# Health check
curl http://localhost:8000/health

# List assets
curl http://localhost:8000/assets

# Generate a plan
curl -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date": "2025-06-01", "hours": 1}'

# Approve the plan (replace PLAN_ID)
curl -X POST http://localhost:8000/plans/{PLAN_ID}/approve

# Trigger prep
curl -X POST http://localhost:8000/prep/run-once

# Start streaming
curl -X POST http://localhost:8000/stream/start

# Generate report
docker compose exec api app reporter --date 2025-06-01
```

### 5. API Docs

Visit http://localhost:8000/docs for the interactive Swagger UI.

## Local Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start Postgres (e.g. via Docker)
docker compose up db -d

# Set env vars
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/voulezvous
export DATABASE_URL_SYNC=postgresql://postgres:postgres@localhost:5432/voulezvous
export SPOOL_ROOT=./spool

# Run migrations
alembic upgrade head

# Run tests
pytest -v

# Run API
app api
```

## CLI Reference

```bash
app seed-demo-data                          # Load demo assets
app planner --date 2025-06-01 --hours 24    # Generate plan
app prep-worker --once                       # Run one prep cycle
app prep-worker --interval 30               # Poll continuously
app streamer                                 # Stream to target
app reporter --date 2025-06-01              # Generate daily report
app api --host 0.0.0.0 --port 8000          # Run API server
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/assets` | Register new asset |
| GET | `/assets` | List assets (filter by kind, rights_status, status) |
| GET | `/assets/{id}` | Get single asset |
| PATCH | `/assets/{id}` | Update asset (approve, block, edit) |
| POST | `/plans/generate` | Generate stream plan |
| GET | `/plans/{id}` | Get plan with items |
| POST | `/plans/{id}/approve` | Approve a draft plan |
| POST | `/prep/run-once` | Trigger one prep cycle |
| POST | `/stream/start` | Start streamer |
| POST | `/stream/stop` | Stop streamer |
| GET | `/stream/status` | Streamer status |
| GET | `/reports/{date}` | Get daily report |

## Rights & Compliance

- Assets start as `rights_status=pending_review`
- Nothing can be prepared or streamed until explicitly marked `approved_for_stream`
- The system only supports:
  - Direct downloadable URLs the operator is authorized to use
  - Operator-uploaded local files
- No scraping, DRM bypass, login harvesting, or technical circumvention

## Environment Variables

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async DB connection |
| `SPOOL_ROOT` | `/spool` | Media spool directory |
| `STREAM_TARGET` | `null` | RTMP URL or "null" for test sink |
| `PREP_LOOKAHEAD_HOURS` | `6` | Hours of content to prepare ahead |
| `DELETE_AFTER_STREAM` | `true` | Delete local bytes after streaming |
| `FALLBACK_VIDEO` | `fallback.mp4` | Fallback file name in spool/fallback/ |

## Data Model

Six tables: `library_assets`, `stream_plans`, `stream_plan_items`, `prep_jobs`, `stream_events`, `daily_reports`.

All use UUIDs as primary keys. See `src/voulezvous/models/tables.py` for the complete schema.

## Spool Layout

```
/spool/
  downloads/    # Raw downloaded files
  prepared/     # Normalized/mixed ready-to-play files
  fallback/     # Fallback holding video
  tmp/          # Temporary processing files
  reports/      # Generated report files
```
