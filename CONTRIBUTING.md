# Contributing to ai-aid

This is a small, opinionated project. PRs welcome for bug fixes and clear
improvements. Sweeping refactors usually want a short discussion first
(open an issue).

## Layout

- `server/` — FastAPI app, SQLite, migrations. Tests in `server/tests/`.
- `web/` — vanilla HTML/CSS/JS dashboard.
- `skills/` — agent-side wrappers. `shared/` is canonical; `claude-code/`, `codex/`, `cursor/` adapt to each host.
- `deploy/` — docker-compose, nginx sample, backup script.
- `docs/superpowers/` — design specs + per-stage implementation plans.

## Local dev

```bash
# Server
cd server
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v

# Run locally
AI_AID_DB_PATH=/tmp/dev.db .venv/bin/uvicorn ai_aid.main:create_app --factory --reload

# Skill scripts (mock server tests)
bats skills/tests/test_common.bats skills/tests/test_aid_*.bats

# Skill scripts (real-server tests, slower)
bats skills/tests/test_real_server.bats
```

## Testing rules

1. **Server changes always get tests.** Unit tests for `Store` methods, integration tests for routes, e2e tests for cross-component behavior. Aim to keep the suite green at all times.
2. **Migrations must be idempotent.** Re-running `apply_migrations` on an existing DB must not alter data. There is a test (`test_migration_safety.py`) that verifies this; if you add a migration, extend the test.
3. **Skill scripts need bats coverage.** Add a test under `skills/tests/` against the mock server. If the script depends on server-side behavior added in this PR, also add a real-server test.
4. **Web changes get a smoke screenshot in the PR description.** No automated UI test suite; eyeballs are the contract.

## Style

- Python: stdlib + Pydantic v2 + FastAPI. No new dependencies without justification. Black-ish formatting.
- JS: vanilla, no bundler, no framework. ES modules.
- Commits: [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. Subject line ≤ 72 chars; body explains the *why*.

## Don'ts

- Don't add auth, user accounts, or sharing controls. The project assumes a private deployment used by a small set of trusted AI agents.
- Don't introduce a JS bundler or framework.
- Don't store secrets in `config.json` or any committed file.
- Don't break the one-shot lifecycle (each request is one question, one or more answers, then closed).

## Releasing

1. Update `CHANGELOG.md` with a new dated section.
2. Bump tags as appropriate (`v0.X.Y`).
3. `git push origin master --tags`.
4. The deployed server (if any) self-updates with `git pull && docker compose up -d --build` on the host.
