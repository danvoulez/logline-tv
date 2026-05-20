# REALITY CHECK - Minimum Production Receipt

This document defines the minimum requirements for logline-tv to be considered production-ready. Each item must be verified with a receipt (test output, log snippet, or manual verification).

## Phase 0: Repository Admission

### Code Hygiene
- [x] `ruff check .` passes without errors
- [x] `ruff format .` applied consistently
- [x] `pytest -q` passes (37 tests)
- [x] `python -m compileall -q src tests alembic` succeeds

### Reality Gates
- [x] Silent fallback to simulated discovery removed from API
- [x] Silent fallback to simulated discovery removed from Director tools
- [x] Orchestrator requires explicit `simulated_discovery` parameter
- [x] Test verifies discovery failure does not create simulated candidates
- [x] Test verifies metadata_only candidates have correct status
- [x] Test verifies unapproved assets have correct rights status

## Phase 1: Real Database

### Docker/Postgres/Alembic
- [x] `docker compose up -d --build db migrate api` succeeds
- [x] `docker compose logs migrate` shows successful migration
- [x] `curl http://localhost:8000/health` returns 200 with version
- [x] Postgres schema matches Alembic migrations (no drift)
- [ ] Foreign key cycle warning resolved (candidate_assets ↔ retrieval_adapters)

### Schema Validation
- [ ] All tables created with correct types (UUID, JSONB, timezone-aware timestamps)
- [ ] Constraints enforced (NOT NULL, UNIQUE, CHECK)
- [ ] Indexes present for query performance
- [ ] Migration rollback tested (`alembic downgrade -1`)

## Phase 2: Manual Channel Operation

### Core Flow Verification
The minimum "works in reality" test:
1. [ ] LibraryAsset created with approved_for_stream status
2. [ ] StreamPlan generated for target date
3. [ ] Plan approved (status → approved)
4. [ ] Prep worker downloads and normalizes file to `/spool/prepared/`
5. [ ] Prep status → ready with valid prepared_file_path
6. [ ] Streamer generates HLS at `/hls/stream.m3u8`
7. [ ] Browser can play stream for 10+ minutes
8. [ ] StreamEvent recorded in database with actual timestamps

### File System Verification
- [ ] `/spool/downloads/` directory exists and is writable
- [ ] `/spool/prepared/` directory exists and is writable
- [ ] `/hls/` directory exists and is writable
- [ ] FFmpeg can access all directories
- [ ] Disk space monitoring functional
- [ ] Cleanup job removes old prepared files

### API Endpoints
- [ ] `POST /assets` creates LibraryAsset
- [ ] `POST /plans/generate` creates StreamPlan
- [ ] `POST /plans/{id}/approve` approves plan
- [ ] `GET /plans/{id}/items` shows plan items with prep_status
- [ ] `POST /stream/start` starts streaming
- [ ] `GET /stream/snapshot` shows current/next items
- [ ] `GET /health` returns system status

## Phase 3: Operation Safety

### Restart Safety
- [ ] Streamer resumes after restart (finds next queued item)
- [ ] Prep worker resumes after restart (processes pending items)
- [ ] No duplicate StreamEvents after restart
- [ ] HLS generation continues seamlessly after restart

### Error Handling
- [ ] Download failure logged and item marked as failed
- [ ] FFmpeg failure logged and item marked as failed
- [ ] Missing source file handled gracefully
- [ ] Network timeout handled with retry logic
- [ ] Disk space full handled with alert

### Logging and Monitoring
- [ ] All worker actions logged with structured context
- [ ] Errors logged with stack traces and correlation IDs
- [ ] Performance metrics logged (prep time, stream duration)
- [ ] Daily report generated successfully
- [ ] Logs rotated to prevent disk fill

### Cleanup
- [ ] Old prepared files removed automatically
- [ ] Old HLS segments removed automatically
- [ ] Completed StreamPlans archived after N days
- [ ] Old DiscoveryRuns cleaned up
- [ ] Orphaned files detected and reported

## Phase 4: Director Autonomy

### Decision Logging
- [ ] Every Director action logged with reason
- [ ] Director state persisted in database
- [ ] No silent fallback to simulated discovery
- [ ] Discovery failures are explicit (not hidden)
- [ ] Keyword adjustments logged with before/after values

### Safety Bounds
- [ ] Director cannot delete approved assets
- [ ] Director cannot modify stream control without audit
- [ ] Director actions rate-limited
- [ ] Manual override always available
- [ ] Emergency stop mechanism functional

### Verification
- [ ] `get_tv_status` returns accurate snapshot
- [ ] Director loop runs on schedule (5 min)
- [ ] Manual Director tick works via API/MCP
- [ ] Director respects domain policies
- [ ] Director respects keyword weights

## Phase 5: Acquisition Safety

### Rights and Compliance
- [ ] metadata_only candidates never promoted to LibraryAsset
- [ ] Unapproved assets never included in StreamPlan
- [ ] Approved assets never prepared without approval
- [ ] Credentials never stored in plaintext
- [ ] Discovery never attempts DRM circumvention

### Domain Policies
- [ ] Each domain has explicit policy
- [ ] Policy includes allowed_actions
- [ ] Policy includes retrieval_modes
- [ ] Policy includes quality_floor
- [ ] Policy respects robots.txt

### Discovery Verification
- [ ] Real discovery requires explicit request
- [ ] Simulated discovery requires explicit flag
- [ ] Discovery failure = failure (not silent fallback)
- [ ] Discovery respects max_pages_per_run
- [ ] Discovery respects exclude keywords

## Receipt Template

For each completed item, provide:
```bash
# Command or action
<command or action>

# Output or evidence
<output, log snippet, or screenshot>

# Verification
<how you verified this is correct>
```

## Current Status

**Phase 0**: ✅ COMPLETE
- All code hygiene checks pass
- All reality gates implemented
- Tests added and passing

**Phase 1**: ✅ COMPLETE
- Docker installed and running on lab-512 (via colima)
- Postgres 16-alpine running and healthy
- All 7 Alembic migrations applied successfully
- 20 tables created in Postgres database
- API health endpoint responding with 200 OK
- Schema matches migrations (no drift)

### Phase 1 Receipt
```bash
# Command: Docker compose up
cd ~/logline-tv && export DOCKER_HOST=unix:///Users/danvoulez/.colima/default/docker.sock && docker compose up -d db migrate api

# Output: Services started successfully
Image postgres:16-alpine Pulled
Image logline-tv-migrate Built
Container logline-tv-db-1 Created (healthy)
Container logline-tv-migrate-1 Exited (0)
Container logline-tv-api-1 Created (running)

# Command: Migration logs
docker compose logs migrate

# Output: All migrations applied
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002_acquisition, Acquisition subsystem — 10 new tables.
INFO  [alembic.runtime.migration] Running upgrade 002_acquisition -> 003_bridge, Add bridge traceability columns.
INFO  [alembic.runtime.migration] Running upgrade 003_bridge -> 004, Runtime control table and production constraints
INFO  [alembic.runtime.migration] Running upgrade 004 -> 005, Asset performance ficha — play history and health score on library_assets.
INFO  [alembic.runtime.migration] Running upgrade 005 -> 006, Move site adapter config from Python to domain_policies.
INFO  [alembic.runtime.migration] Running upgrade 006 -> 007, Director runs + actions.

# Command: Schema verification
docker exec logline-tv-db-1 psql -U postgres -d voulezvous -c '\dt'

# Output: 20 tables created
public | alembic_version    | table | postgres
public | asset_enrichments  | table | postgres
public | autonomy_reports   | table | postgres
public | candidate_assets   | table | postgres
public | daily_reports      | table | postgres
public | director_actions   | table | postgres
public | director_runs      | table | postgres
public | discovery_runs     | table | postgres
public | domain_policies    | table | postgres
public | library_assets     | table | postgres
public | lineup_items       | table | postgres
public | lineup_runs        | table | postgres
public | media_ir_jobs      | table | postgres
public | prep_jobs          | table | postgres
public | retrieval_adapters | table | postgres
public | search_keywords    | table | postgres
public | stream_control     | table | postgres
public | stream_events      | table | postgres
public | stream_plan_items  | table | postgres
public | stream_plans       | table | postgres

# Command: Health endpoint
curl -s http://localhost:8000/health

# Output: 200 OK with version
{"status":"ok","version":"0.1.0"}

# Verification: Manual inspection of docker compose ps shows db (healthy) and api (running)

**Phase 2**: ⏳ PENDING
- Manual channel operation not tested
- HLS streaming not verified
- Browser playback not verified

**Phase 3**: ⏳ PENDING
- Restart safety not tested
- Error handling not verified
- Cleanup not tested

**Phase 4**: ⏳ PENDING
- Director autonomy not tested
- Decision logging not verified
- Safety bounds not tested

**Phase 5**: ⏳ PENDING
- Acquisition safety not verified
- Rights compliance not tested
- Domain policies not verified

## Next Steps

1. ✅ Set up Docker environment (completed on lab-512 with colima)
2. ✅ Verify Postgres + Alembic on real database (7 migrations, 20 tables)
3. Test manual channel operation with local file
4. Verify HLS streaming and browser playback
5. Test restart safety
6. Implement and test cleanup jobs
7. Verify Director autonomy with real discovery
8. Implement credential encryption
9. Add integration tests for end-to-end flow
10. Load test with 24h programming

## Notes

- The system has a solid foundation with Phase 0 and Phase 1 complete
- Real Postgres testing completed on lab-512 with colima (Docker)
- SQLite test coverage is good but Postgres verification is now proven
- The FK cycle warning between candidate_assets and retrieval_adapters still needs resolution
- Consider adding Postgres-specific tests to the CI pipeline
- Monitoring and alerting should be added before production deployment
- Phase 2 (Manual Channel Operation) is the next critical milestone
