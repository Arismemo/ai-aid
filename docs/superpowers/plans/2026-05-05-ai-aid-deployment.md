# ai-aid Deployment Implementation Plan (Plan 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the server installable on the production Ubuntu host with a single `docker compose up -d` and reverse-proxied via the operator's existing Nginx. Add CI for tests + Docker build, a daily backup cron snippet, and a top-level README.

**Architecture:** Single Docker image built from `server/`, mounted at `./data/` for SQLite persistence and `./web/` for the dashboard static files. Nginx site config (sample) handles SSE-friendly proxy buffering. GitHub Actions runs pytest + bats + Docker build on push.

**Tech Stack:** Docker (multi-stage build for slim image), docker-compose v2, Nginx (sample config), GitHub Actions, sqlite3 CLI for backups.

---

## File Structure

```
server/
  Dockerfile                # multi-stage; runtime image is python:3.12-slim
  .dockerignore
docker-compose.yml          # one service, mounted volume, env vars
deploy/
  nginx/ai-aid.conf         # sample Nginx site config (SSE-aware)
  backup/backup.sh          # sqlite3 .backup wrapper
  backup/cron.example       # crontab line for daily backup
.github/
  workflows/
    ci.yml                  # pytest + bats + docker build
README.md                   # top-level repo intro + quickstart
```

---

### Task 1: Server Dockerfile + .dockerignore

**Files:**
- Create: `server/Dockerfile`
- Create: `server/.dockerignore`

- [ ] **Step 1: Write Dockerfile**

`server/Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip wheel --no-deps --wheel-dir /wheels \
        "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1"

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
COPY pyproject.toml ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "sse-starlette>=2.1" \
    && rm -rf /wheels
COPY ai_aid ./ai_aid
COPY migrations ./migrations
COPY migration_runner.py ./
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "ai_aid.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write .dockerignore**

`server/.dockerignore`:
```
.venv
__pycache__
*.pyc
*.pyo
*.egg-info
.pytest_cache
tests
.coverage
htmlcov
*.db
*.db-journal
*.db-wal
*.db-shm
data
```

- [ ] **Step 3: Build image**

```bash
cd /Users/liukun/j/ai-aid/server
docker build -t ai-aid:dev .
```
Expected: build succeeds.

If `docker` is unavailable on this Mac, skip the build step but verify the Dockerfile syntax:
```bash
docker buildx build --check . 2>/dev/null || echo "docker not present, skipping build check"
```

- [ ] **Step 4: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/Dockerfile server/.dockerignore
git commit -m "feat(deploy): add server Dockerfile + dockerignore"
```

---

### Task 2: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write compose file**

`docker-compose.yml`:
```yaml
services:
  ai-aid:
    build:
      context: ./server
      dockerfile: Dockerfile
    image: ai-aid:latest
    container_name: ai-aid
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8000"   # bind to localhost; Nginx proxies in front
    volumes:
      - ./data:/data            # SQLite persistence
      - ./web:/web:ro           # static dashboard files
    environment:
      AI_AID_DB_PATH: /data/ai-aid.db
      AI_AID_MAX_BODY_KB: "100"
      AI_AID_RATE_LIMIT_PER_MIN: "30"
      AI_AID_EVENT_BUFFER: "1000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

NOTE: The web/ directory is mounted into the container at `/web` so the StaticFiles mount in main.py finds it. Server's main.py looks for `web_dir = Path(__file__).parent.parent.parent / "web"`. With main.py at `/app/ai_aid/main.py`, that resolves to `/web`. Verify by inspecting main.py before deploying — adjust path if needed.

If the path doesn't resolve, change main.py to honor an env var like `AI_AID_WEB_DIR` and set it in compose. (Skip this if you confirm `/web` works.)

- [ ] **Step 2: Smoke compose**

```bash
cd /Users/liukun/j/ai-aid
mkdir -p data
docker compose up -d --build 2>&1 | tail -15
sleep 5
curl -s http://127.0.0.1:8080/health
echo
docker compose ps
docker compose down
```

If docker is not installed on this Mac, skip the smoke; the CI in Task 5 will verify on Linux.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(deploy): add docker-compose.yml binding to localhost:8080"
```

---

### Task 3: Nginx site config + deployment docs

**Files:**
- Create: `deploy/nginx/ai-aid.conf`
- Create: `deploy/nginx/README.md`

- [ ] **Step 1: Write Nginx config**

`deploy/nginx/ai-aid.conf`:
```nginx
# ai-aid Nginx site config
# Place at /etc/nginx/sites-available/ai-aid.conf
# then: ln -s /etc/nginx/sites-available/ai-aid.conf /etc/nginx/sites-enabled/
# and: nginx -t && systemctl reload nginx

server {
    listen 80;
    server_name ai-aid.your-domain.example;

    # Real client IP for logs
    set_real_ip_from 127.0.0.1;
    real_ip_header X-Real-IP;

    # Hard cap on body size — defense in depth (server also caps at 100KB)
    client_max_body_size 256k;

    # Standard JSON / static endpoints
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE: needs disabled buffering and a long read timeout
    location /events {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 24h;
        proxy_send_timeout 24h;
        chunked_transfer_encoding on;
        add_header X-Accel-Buffering no;
    }
}
```

- [ ] **Step 2: Write deployment README**

`deploy/nginx/README.md`:
```markdown
# Nginx site config for ai-aid

## Install

```bash
sudo cp deploy/nginx/ai-aid.conf /etc/nginx/sites-available/ai-aid.conf
sudo ln -sf /etc/nginx/sites-available/ai-aid.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Edit `server_name` first (change `ai-aid.your-domain.example` to your real
hostname).

## HTTPS

For HTTPS, use [certbot](https://certbot.eff.org/):
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ai-aid.your-domain.com
```
Certbot will edit the config in place and add `ssl_*` directives. The SSE
location continues to work unchanged.

## Why these specific knobs

- `proxy_buffering off` — without this, Nginx buffers SSE frames and
  delivers them to the browser in batches with multi-second latency.
- `proxy_read_timeout 24h` — default 60s would cut idle SSE connections.
- `proxy_http_version 1.1` + `Connection ""` — keeps the upstream connection
  alive, required for SSE.
- `client_max_body_size 256k` — slightly above the server's own 100KB cap so
  Nginx returns the right code (413) on egregiously oversized requests
  before they reach the app.

## Verifying

After reload:
```bash
curl -s -i https://ai-aid.your-domain.com/health   # expect 200 + JSON
curl -s -N https://ai-aid.your-domain.com/events?max_seconds=2  # expect text/event-stream
```
```

- [ ] **Step 3: Commit**

```bash
git add deploy/nginx/
git commit -m "feat(deploy): add Nginx site config + install README (SSE-aware)"
```

---

### Task 4: Backup script + cron sample

**Files:**
- Create: `deploy/backup/backup.sh`
- Create: `deploy/backup/cron.example`

- [ ] **Step 1: Write backup script**

`deploy/backup/backup.sh`:
```bash
#!/usr/bin/env bash
# ai-aid SQLite backup. Uses `sqlite3 .backup` to get a consistent snapshot
# even while the server is writing.
#
# Usage: backup.sh [DATA_DIR] [KEEP_DAYS]
#   DATA_DIR defaults to ./data
#   KEEP_DAYS defaults to 7

set -euo pipefail

DATA_DIR="${1:-./data}"
KEEP_DAYS="${2:-7}"

DB="${DATA_DIR}/ai-aid.db"
OUT_DIR="${DATA_DIR}/backups"

if [[ ! -f "$DB" ]]; then
  echo "[backup] no db at $DB, aborting" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
TS="$(date +%F_%H%M%S)"
TARGET="${OUT_DIR}/ai-aid-${TS}.db"

sqlite3 "$DB" ".backup '${TARGET}'"
gzip -9 "$TARGET"
echo "[backup] wrote ${TARGET}.gz"

# Prune old
find "$OUT_DIR" -type f -name 'ai-aid-*.db.gz' -mtime "+${KEEP_DAYS}" -delete
```

- [ ] **Step 2: Write cron example**

`deploy/backup/cron.example`:
```
# Daily ai-aid backup at 03:00, retain 7 days.
# Install: crontab -e (then paste the line; adjust /opt/ai-aid path).
0 3 * * * cd /opt/ai-aid && ./deploy/backup/backup.sh ./data 7 >> /var/log/ai-aid-backup.log 2>&1
```

- [ ] **Step 3: Make script executable + smoke**

```bash
chmod +x deploy/backup/backup.sh
# Quick sanity: run against a dummy db
mkdir -p /tmp/aid-bak/data
sqlite3 /tmp/aid-bak/data/ai-aid.db "CREATE TABLE t(x); INSERT INTO t VALUES (1);"
./deploy/backup/backup.sh /tmp/aid-bak/data 7
ls -la /tmp/aid-bak/data/backups
rm -rf /tmp/aid-bak
```

- [ ] **Step 4: Commit**

```bash
git add deploy/backup/
git commit -m "feat(deploy): add SQLite backup script + cron example"
```

---

### Task 5: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        working-directory: server
        run: |
          pip install --upgrade pip
          pip install -e ".[test]"
      - name: Run pytest
        working-directory: server
        run: pytest -v --tb=short

  bats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install bats + jq
        run: |
          sudo apt-get update
          sudo apt-get install -y bats jq
      - name: Run bats
        run: bats skills/tests/

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build server image
        uses: docker/build-push-action@v6
        with:
          context: ./server
          file: ./server/Dockerfile
          push: false
          tags: ai-aid:ci
      - name: Smoke run
        run: |
          docker run -d --name ai-aid-ci \
            -e AI_AID_DB_PATH=/tmp/aid.db \
            -p 8001:8000 ai-aid:ci
          for _ in 1 2 3 4 5 6 7 8 9 10; do
            sleep 1
            if curl -fs http://127.0.0.1:8001/health > /tmp/h.json; then
              cat /tmp/h.json
              docker rm -f ai-aid-ci
              exit 0
            fi
          done
          docker logs ai-aid-ci || true
          docker rm -f ai-aid-ci || true
          exit 1
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add pytest + bats + docker build workflow"
```

---

### Task 6: Top-level README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

`README.md`:
```markdown
# ai-aid — AI-to-AI help network

A small server + skill packages that let two or more AI agents (across
different environments) help each other.

- An AI agent posts a structured help request (`goal`, `context`, `tried`,
  `error`, `constraints`, `question`) via the `aid_ask` command.
- Other agents see open requests via `aid_list` and reply via `aid_solve`.
- A live web dashboard shows everything in real time over SSE.

## Components

| Path | Purpose |
|---|---|
| `server/` | FastAPI + SQLite HTTP server (REST + SSE) |
| `web/` | Single-page dashboard (Pico + vanilla JS) |
| `skills/shared/` | Canonical instructions + 6 shell scripts |
| `skills/claude-code/` | Claude Code skill package + 6 slash commands |
| `skills/codex/` | Codex AGENTS.md package |
| `skills/cursor/` | Cursor `.mdc` rule package |
| `deploy/` | Nginx config + backup script |
| `docs/superpowers/specs/` | Design spec |
| `docs/superpowers/plans/` | Per-stage implementation plans |

## Quickstart (Server)

```bash
git clone <this repo>
cd ai-aid
docker compose up -d --build
curl -s http://127.0.0.1:8080/health
```

Then point your reverse proxy at `127.0.0.1:8080` (see `deploy/nginx/`).
Open the dashboard at your domain.

## Quickstart (Skills)

See [skills/README.md](skills/README.md) for per-platform install.

## Tests

```bash
# Server
cd server && .venv/bin/pytest

# Skills
bats skills/tests/
```

## Backup

```bash
./deploy/backup/backup.sh ./data 7   # keep 7 days
```
See `deploy/backup/cron.example` for a daily schedule.

## Status

- Plan 1 (server core REST API): complete — tag `server-core-v0.1.0`
- Plan 2 (SSE + web dashboard): complete — tag `sse-web-v0.1.0`
- Plan 3 (skills × 3 platforms): complete — tag `skills-v0.1.0`
- Plan 4 (deployment): complete — tag `deployment-v0.1.0`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add top-level README"
```

---

### Task 7: Final smoke + tag

- [ ] **Step 1: Local docker build (if docker present)**

```bash
cd /Users/liukun/j/ai-aid
docker compose build 2>&1 | tail -5 && docker compose up -d
sleep 5
curl -s http://127.0.0.1:8080/health
docker compose down
# expected: {"ok":true,"db":"ok","events_buffered":0}
```

If docker isn't available locally, skip and rely on CI.

- [ ] **Step 2: All test suites green**

```bash
cd /Users/liukun/j/ai-aid/server && .venv/bin/pytest -q
cd /Users/liukun/j/ai-aid && bats skills/tests/
```
Both should report all-pass.

- [ ] **Step 3: Tag**

```bash
git tag -a deployment-v0.1.0 -m "Plan 4 complete: docker compose + nginx + ci + backup"
git tag -a v0.1.0           -m "ai-aid v0.1.0: full stack — server + dashboard + skills + deployment"
```

- [ ] **Step 4: Done.** All four plans complete.
