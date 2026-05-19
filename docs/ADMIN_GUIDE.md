# voulezvous.tv — Admin Guide

**Audience:** Dan. The only human who touches this.
**URL:** https://tv.logline.world/admin

---

## What this thing does

It's a 24/7 streaming TV channel that runs itself. You provide:
- Sites to scrape (domains + selectors + optional credentials)
- Keywords to search for

The rest is automatic: the Director (LLM loop) discovers content, approves candidates, generates broadcast plans, and keeps FFmpeg pointed at Cloudflare. You never touch the server.

---

## The full cycle (so you understand what's happening)

```
You add a site + keywords
        ↓
Director runs every 5 min
        ↓
[every 6h] run_discovery → scrapes sites with keywords → CandidateAssets saved
        ↓
Director: promote_candidate → CandidateAsset becomes LibraryAsset (approved)
        ↓
Director: generate_plan → 24h broadcast schedule created from library
        ↓
prep-worker: downloads + normalizes videos into /spool/prepared
        ↓
streamer: plays files via FFmpeg → HLS at /spool/hls/stream.m3u8
        ↓
Cloudflare Tunnel → tv.logline.world serves the HLS stream
        ↓
Director watchdog: if heartbeat stale > 3min → restart streamer
        ↓
[when queue < 4h] Director: generate_plan again → cycle repeats
```

---

## The 3 things you actually do

### 1. Add a site

Admin → Discovery tab → **+ Add Site**

Fill in:
| Field | What it is | Example |
|-------|-----------|---------|
| Domain | Just the hostname | `xvideos.com` |
| Search URL template | Where to search | `https://xvideos.com/?k={query}` |
| Result selector | CSS selector for links | `.thumb-block a.thumb` |
| Title selector | CSS selector for title | `h1, .video-title` |
| Adult site | Check it | ✓ |
| Requires login | Check if site needs account | ✓ |
| Login URL | The login page | `https://xvideos.com/login` |
| Email selector | CSS of email input | `input[name='email']` |
| Password selector | CSS of password input | `input[type='password']` |
| Submit selector | CSS of login button | `button[type='submit']` |
| Credential email | Your account email | — |
| Credential password | Your account password | — |

**You don't need all fields.** A site without login credentials will browse anonymously. A site without a search template won't run keyword searches (only user-profile scraping, if you configure a user URL template).

The password is stored in Postgres on the LAB. It never comes back through the API.

### 2. Add keywords

Admin → Discovery → **Search Keywords** card

Type the keyword, pick weight (1.0 = normal, 2.0 = twice as likely to use), choose Include or Exclude, click Add.

The Director can also add keywords itself via `add_keyword` when it detects gaps. You can pause any keyword by clicking Pause next to it.

### 3. Check status

Admin → **Observabilidade** tab

- **Sinal** — green dot = live, amber = fallback (no content queued), red = off
- **Pipeline** — how many hours are queued + disk usage
- **Diretor** — last 30 decisions (what the LLM decided and why)
- **Saúde** — Ollama reachable, last discovery run

If everything is green and the queue shows > 4h: the channel is fine, close the tab.

---

## When to intervene

### Stream is in FALLBACK

**Meaning:** streamer is running but the plan has no ready items.
**Check:** Observabilidade → Pipeline → "Fila" shows 0h.
**Fix:** The Director should auto-generate a plan. Wait 5 min. If still 0h, click "Forçar rodada" in Observabilidade.

If the library has no approved videos at all, the Director can't generate a plan. Check Assets tab — if everything is `pending_review`, click Approve on a few.

### Stream is OFF

**Check:** Observabilidade → Sinal shows red.
**Fix:** The Director will call `start_stream` on the next tick (< 5 min). If it doesn't recover, click "Forçar rodada".

If it still doesn't start after a forced tick, SSH to the LAB:
```bash
ssh lab-8gb
cd ~/tv-today
docker compose ps          # check all 5 containers are Up
docker compose logs streamer --tail 30
```

### Discovery finds nothing

**Check:** Observabilidade → Saúde → "último discovery" — if it's showing "nunca" or > 12h ago and the queue is still empty, something is wrong.
**Common causes:**
- No sites with search templates configured
- All sites are disabled (Admin → Discovery, check Enabled toggle)
- No active keywords (Admin → Discovery → Keywords list)

### Site credentials expired

Admin → Discovery → click **Edit** on the site → update the password → Save. The next discovery run will use the new credentials.

### You want to block a bad video

Admin → Assets → find it → click Block. The Director will also auto-block assets that keep failing (health_score < 0.3 after 3+ plays).

---

## Admin tabs reference

| Tab | What's there |
|-----|-------------|
| Dashboard | Live signal status + pending candidates |
| Assets | Full library: videos, music, bumpers. Approve/block manually. |
| Discovery | Sites, keywords, candidates, recent discovery runs |
| Plans | All broadcast plans. Click a row to see item list. |
| Reports | Auto-generated daily reports. Click a row to read. |
| Observabilidade | Live ops dashboard. Use this daily. |

---

## What you never need to touch

- `.env` — all configuration is in Postgres now
- `docker-compose.yml` — containers restart themselves
- SSH — unless containers are completely dead
- Alembic migrations — only when you're adding a new feature
- The Director's decision logic — it learns from what you curate

---

## Containers and what they do

| Container | Role |
|-----------|------|
| `api` | FastAPI — serves /admin, all REST endpoints, HLS |
| `db` | Postgres — all state lives here |
| `prep-worker` | Downloads videos + normalizes them for streaming |
| `streamer` | FFmpeg loop — reads plan, plays files, outputs HLS |
| `director` | LLM loop — runs every 5min, makes all autonomous decisions |

All 5 must be `Up` for the channel to function. Check with:
```bash
docker compose -f ~/tv-today/docker-compose.yml ps
```

---

## Useful curl commands

```bash
# Is the API alive?
curl https://tv.logline.world/health

# Current stream status
curl https://tv.logline.world/stream/status

# Last 5 director decisions
curl https://tv.logline.world/director/actions?limit=5

# Force a director tick now
curl -X POST https://tv.logline.world/director/tick

# All sites configured
curl https://tv.logline.world/domain-policies

# Full observability snapshot
curl https://tv.logline.world/obs/snapshot | python3 -m json.tool
```
