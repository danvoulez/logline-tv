# Voulezvous Runbook

## Daily Operations

### Normal Day

1. **Assets already loaded and approved** — check with `GET /assets?rights_status=approved_for_stream`
2. **Generate plan**: `app planner --date YYYY-MM-DD --hours 24`
3. **Approve plan**: `POST /plans/{id}/approve`
4. **Prep worker runs automatically** (or `app prep-worker --once`)
5. **Streamer picks up ready items** (or `POST /stream/start`)
6. **End of day**: `app reporter --date YYYY-MM-DD`

### Adding New Content

1. Register: `POST /assets` with `kind`, `title`, `source_type`, `source_url`
2. Asset starts as `pending_review` — nothing happens yet
3. Review and approve: `PATCH /assets/{id}` with `rights_status: approved_for_stream`
4. Asset is now eligible for planning

### Emergency: Streamer Down

1. Check status: `GET /stream/status`
2. Restart: `docker compose restart streamer`
3. Streamer resumes from next queued item automatically
4. Fallback video plays if no items are ready

### Storage Pressure

1. Check report: `GET /reports/YYYY-MM-DD` for storage estimates
2. Old prepared files auto-delete if `delete_after_stream=true`
3. Manual cleanup: remove files in `/spool/downloads/` and `/spool/prepared/`
4. Metadata stays in the database regardless of file deletion

### Prep Failures

1. Check report for `prep_failures` count
2. Look at `prep_jobs` table for error messages
3. Common causes: broken source URLs, FFmpeg errors, disk full
4. Fix source and re-queue by resetting `prep_status=queued` on the plan item

## Restart Safety

All processes are designed to be restart-safe:

- **API**: Stateless, restart anytime
- **Prep worker**: Picks up from last queued item
- **Streamer**: Resumes from next queued item in the plan
- **Reporter**: Idempotent, re-running overwrites previous report for the same date

## Monitoring

- `GET /health` — basic liveness check
- Structured JSON logs from all processes
- Daily report summarizes the full picture
- No realtime dashboard required for MVP

## Fallback Media

Place a holding video at `/spool/fallback/fallback.mp4`. The streamer uses this when:
- No plan items are ready
- A prepared file is missing
- Between plan items

## Database Backup

The Postgres database is the single source of truth. Back it up regularly:

```bash
docker compose exec db pg_dump -U postgres voulezvous > backup_$(date +%Y%m%d).sql
```
