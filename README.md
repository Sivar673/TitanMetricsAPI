# Titan Metrics API

FastAPI backend for the Titan Metrics coaching app (frontend lives in
`../titan-metrics`).

## Run

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py                     # dev data: 1 coach, 6 clients, 10 weeks
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Interactive docs at http://localhost:8000/docs.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | Dev-stub login (no passwords yet) |
| POST | `/check-ins` | Weekly client check-in (409 on duplicate week) |
| POST | `/workouts` | Log a training session |
| GET | `/coach/clients` | Roster with status + weekly deltas |
| GET | `/clients/{id}/report` | Week-over-week report + coach flags |
| GET | `/clients/{id}/progression` | Weight trajectory + est-1RM trends |

Response shapes mirror `src/types/api.ts` in the frontend repo; that file
is the shared contract.
# TitanMetricsAPI
