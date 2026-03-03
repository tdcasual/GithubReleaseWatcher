# GitHub Release Watcher V2

V2 is a breaking-clean release. Runtime supports only `/api/v2/*`.

## Requirements

- Python 3.12+
- Node.js 20+ (frontend build and tests)

## Run API Server

```bash
python3 watcher.py --web --db-path ./v2.sqlite3 --auth-username admin --auth-password change-me
```

Auth credentials are required. You can pass them via CLI flags or environment variables:

```bash
export GRW_AUTH_USERNAME=admin
export GRW_AUTH_PASSWORD=change-me
python3 watcher.py --web --db-path ./v2.sqlite3
```

## API Surface (V2)

- `GET /api/v2/health`
- `POST /api/v2/auth/login`
- `POST /api/v2/auth/logout`
- `POST /api/v2/jobs`
- `GET /api/v2/jobs`
- `POST /api/v2/jobs/{job_id}/events`
- `GET /api/v2/events`
- `POST /api/v2/repos`
- `GET /api/v2/repos`
- `PUT /api/v2/settings`
- `GET /api/v2/settings`
- `GET /api/v2/storage/health`

## One-Time Offline Migration

Use the offline migration helper to generate import report from legacy state data:

```python
from pathlib import Path
from scripts.migrate_v1_to_v2 import run_import

run_import(
    config_path=Path("config.toml"),
    state_path=Path("state.json"),
    db_path=Path("v2.sqlite3"),
    report_path=Path("migration-report.json"),
)
```

## Frontend Source of Truth

The frontend source lives only in `frontend/`.
Build output is generated into `deploy/vercel/public` via Vite.

```bash
cd frontend
npm install
npm test
npm run build
```

## CI/Verification

```bash
python3 -m pytest -q
cd frontend && npm install && npm test && npm run build
```

Expected: tests pass.
