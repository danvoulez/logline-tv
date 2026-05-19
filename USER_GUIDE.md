# Voulezvous — User Guide

## What is this?

Voulezvous is a curated, non-realtime streaming engine. You load video content, approve it, generate a daily broadcast plan, prepare the files, and stream them to your audience. Everything is planned ahead of time — no live improvisation.

**Lifecycle:** Library → Plan → Prepare → Stream → Log → Cleanup → Report

---

## Quick Start (5 minutes)

### 1. Start the system

```bash
cd tv-today
cp .env.example .env     # Edit if needed (defaults work for local use)
docker compose up -d --build
```

Wait for all services to start:
```bash
docker compose ps
# Expected: db (healthy), api (Up), prep-worker (Up), streamer (Up)
```

### 2. Open the admin dashboard

Go to **http://localhost:8000/admin** in your browser.

Everything you need is here: add assets, approve them, generate plans, monitor prep, and view reports.

### 3. Add your first video

In the admin dashboard, click **"Add Asset"** and fill in:
- **Title**: A name for the video
- **Kind**: `video`
- **Source Type**: `direct_url` (paste a URL) or `uploaded_file` (local path on the server)
- **Source URL**: The direct download link to the video file
- **Duration**: Video length in seconds

Or via the API:
```bash
curl -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "video",
    "title": "My First Video",
    "source_type": "direct_url",
    "source_url": "https://example.com/my-video.mp4",
    "duration_sec": 600
  }'
```

### 4. Approve the video for streaming

Every asset starts as **pending_review**. Nothing can be planned or streamed until you explicitly approve it.

In the dashboard, find the asset and click **"Approve"**. Or via the API:
```bash
curl -X PATCH http://localhost:8000/assets/{asset_id} \
  -H "Content-Type: application/json" \
  -d '{"rights_status": "approved_for_stream"}'
```

### 5. Generate a broadcast plan

Create a plan for a specific date and duration. The planner picks from approved assets, avoids immediate repeats, and fills the time window.

In the dashboard, click **"Generate Plan"**, pick a date and hours. Or via the API:
```bash
curl -X POST http://localhost:8000/plans/generate \
  -H "Content-Type: application/json" \
  -d '{"plan_date": "2025-06-01", "hours": 24}'
```

### 6. Approve the plan

Review the generated plan. If it looks good, approve it to begin preparation.

Dashboard: click **"Approve Plan"**. Or:
```bash
curl -X POST http://localhost:8000/plans/{plan_id}/approve
```

### 7. Prepare the content

Once a plan is approved, the prep worker automatically picks up queued items. It:
1. Downloads the source video
2. Normalizes to house format (H.264, AAC, 1080p, 30fps, 48kHz)
3. Optionally mixes background music at 50/50 volume
4. Produces a ready-to-play prepared file

The prep worker runs continuously in the background. You can also trigger a manual cycle:
```bash
curl -X POST http://localhost:8000/prep/run-once
```

### 8. Stream it

The streamer reads prepared files and plays them in sequence. Output goes to the configured stream target (HLS for local TV, RTMP for external, or null for testing).

The streamer runs as a background Docker service. Monitor it in the dashboard.

### 9. Watch on your TV

Open **http://your-machine-ip:8000/** on your TV browser. You'll see the voulezvous player — black background, centered video, hot pink play button.

---

## Daily Operations

### Morning routine
1. Check yesterday's **daily report** (dashboard → Reports, or `GET /reports/YYYY-MM-DD`)
2. Review any failed items or excessive fallback usage
3. Add new content if needed
4. Generate tomorrow's plan
5. Approve the plan

### Adding content
- **Videos**: Add via dashboard or `POST /assets` with `kind=video`
- **Music (DJ sets)**: Add with `kind=music` — these play across video segments at 50/50 volume, no sync needed
- **Brand bumpers**: Add with `kind=bumper` — short branded clips that play between content items

### Rights & Approval
Every asset must be explicitly approved before it can be used:
- `pending_review` → just registered, cannot be used
- `approved_for_stream` → approved for broadcast, eligible for planning
- `blocked` → rejected, will never be used

This is intentional. The system does not assume any content is cleared for rebroadcast. You must verify rights yourself and then approve.

### Music mixing
Music assets (DJ sets) play underneath video content:
- Default: 50/50 volume split (video audio at 50%, music at 50%)
- Music plays continuously across video segments — no synchronization
- Enable when generating a plan: set `mix_music=true`

### Brand bumpers
Short branded clips (logo animations, station IDs) inserted between content items:
- Add as regular assets with `kind=bumper`
- Approve them like any other asset
- The planner automatically inserts approved bumpers between video segments

---

## Configuration

All settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/voulezvous` | Postgres connection (async) |
| `SPOOL_ROOT` | `/spool` | Local media storage root |
| `STREAM_TARGET` | `null` | Output target: `null` (test), `hls` (local), or RTMP URL |
| `FALLBACK_VIDEO` | `fallback.mp4` | Fallback file name in `/spool/fallback/` |
| `PREP_LOOKAHEAD_HOURS` | `6` | How many hours ahead to prepare |
| `DELETE_AFTER_STREAM` | `true` | Delete local bytes after streaming |
| `HOUSE_RESOLUTION` | `1920x1080` | Output video resolution |
| `HOUSE_FRAME_RATE` | `30` | Output frame rate |
| `HOUSE_AUDIO_SAMPLE_RATE` | `48000` | Output audio sample rate |
| `CLOUDFLARE_ACCOUNT_ID` | _(empty)_ | Cloudflare account for R2 upload |
| `CLOUDFLARE_R2_BUCKET` | `voulezvous-hls` | R2 bucket for HLS segments |
| `CLOUDFLARE_R2_ACCESS_KEY` | _(empty)_ | R2 API access key |
| `CLOUDFLARE_R2_SECRET_KEY` | _(empty)_ | R2 API secret key |

---

## Architecture

```
┌─────────────┐
│   Browser   │  TV / viewer opens http://your-ip:8000/
│  (Client)   │  Plays HLS stream via HTML5 video player
└──────┬──────┘
       │
┌──────┴──────┐
│  FastAPI    │  API + Admin Dashboard + Client Page
│  (API)      │  Port 8000
└──────┬──────┘
       │
┌──────┴──────┐
│  Postgres   │  All state, history, metadata
│  (DB)       │  Port 5432
└─────────────┘

Background workers (same codebase, separate processes):
- prep-worker: polls DB for queued items, downloads + normalizes
- streamer: plays prepared files to HLS/RTMP/null target
```

### Storage layout
```
/spool/
  downloads/    ← raw source files
  prepared/     ← normalized ready-to-play files
  hls/          ← HLS segments (.ts) and playlists (.m3u8)
  fallback/     ← static fallback video
  tmp/          ← working space
  reports/      ← generated report files
```

---

## Cloudflare CDN Setup

For internet-accessible streaming:

1. **Your machine** does all heavy processing (prep, normalize, HLS segments)
2. **Cloudflare R2** stores the HLS segments (cheap object storage)
3. **Cloudflare CDN** serves them globally via your domain

### Setup steps:
1. Create a Cloudflare R2 bucket named `voulezvous-hls`
2. Generate R2 API credentials (Account → R2 → Manage API tokens)
3. Set env vars: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY`, `CLOUDFLARE_R2_SECRET_KEY`
4. Connect your domain (voulezvous.tv) to Cloudflare
5. The system auto-uploads HLS segments after preparation

### Cost estimate:
- R2 free tier: 10GB storage, 10M requests/month
- For a 24/7 stream: ~$1-5/month depending on viewer count
- All CPU work is local — zero cloud compute cost

---

## Troubleshooting

### "No approved video assets available for planning"
You need at least one video asset with `rights_status=approved_for_stream`. Check the dashboard or `GET /assets` to see what you have.

### Prep is slow
Each item requires download + FFmpeg normalization (~10-20 seconds per clip). For many items, this takes time. Check `docker compose logs prep-worker` for progress.

### Stream shows fallback only
The fallback plays when no prepared items are ready. Check:
- Is the plan approved? (status must be `approved` or `ready`)
- Are items prepared? (check prep_status in the dashboard)
- Is there a fallback.mp4 in `/spool/fallback/`?

### Container won't start
```bash
docker compose logs <service-name>   # Check the logs
docker compose down && docker compose up -d --build  # Clean restart
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/assets` | Register a new asset |
| `GET` | `/assets` | List all assets (filterable by kind, status) |
| `GET` | `/assets/{id}` | Get single asset |
| `PATCH` | `/assets/{id}` | Update asset (approve, block, edit) |
| `POST` | `/plans/generate` | Generate a new plan |
| `GET` | `/plans/{id}` | Get plan with items |
| `POST` | `/plans/{id}/approve` | Approve a draft plan |
| `POST` | `/prep/run-once` | Trigger one prep cycle |
| `POST` | `/stream/start` | Start the streamer |
| `POST` | `/stream/stop` | Stop the streamer |
| `GET` | `/stream/status` | Get streamer status |
| `GET` | `/reports/{date}` | Get daily report |
| `GET` | `/admin` | Admin dashboard |
| `/` | Client player page |
