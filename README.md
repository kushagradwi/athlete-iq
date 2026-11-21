# ATHLETE IQ

*Your performance has patterns. We find them.*

Upload a workout file (FIT / TCX / GPX / CSV). ATHLETE IQ normalises the telemetry, computes metrics from a
**305-definition registry**, compares the run with your own comparable history, and surfaces
**evidence-backed micro-discoveries** like:

> **Lower heart rate at 5:45/km.** For 10:13 your HR averaged 137 bpm. Across 20 comparable efforts (same pace ±3%,
> similar duration, gradient and temperature) the median was … *Experiment → repeat within 7 days; success if HR ≤ …*

The discoveries are deterministic: statistics run first and the LLM only explains them. Every AI claim must cite
evidence ids, and any number not found in the evidence is dropped.

## Run it

```bash
cd ~/athlete-iq
docker compose up -d --build          # Postgres :5433, Redis, API :8000, worker, web :3000
open http://localhost:3000            # click "Load demo athlete", or drop your own files
```

* Optional: `GEMINI_API_KEY=... docker compose up -d` turns on Gemini. Without a key, a deterministic
  responder answers from the same evidence tools, and the UI says so.
* Optional GoldenCheetah: keep GoldenCheetah open with *Preferences → General → Enable API Web Services*, and add
  `./gc-autoimport` as the athlete's *Auto Import* folder. Every upload is copied there, and once GoldenCheetah has
  imported it, its metrics are compared with ours (`golden_cheetah_sync`).
* API docs: http://localhost:8000/docs

Backend dev and tests (SQLite, synchronous jobs):

```bash
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q      # 58 tests
```

## How it fits together

```
upload ─► analysis_jobs (Redis/Dramatiq worker, idempotent by file hash, retryable)
  parse (fitdecode / lxml / gpxpy / csv) ─► normalise to 1 Hz canonical stream
  (duplicates, out-of-order samples, GPS jumps, gaps, unit errors, per-leg cadence, provenance, quality score)
  ─► metric engine (registry → calculators → CALCULATED / ESTIMATED / INSUFFICIENT_DATA / NOT_APPLICABLE / INVALID_INPUT)
  ─► effort segments (km splits, steady efforts, intervals) ─► 5 personal-baseline indexes
  ─► 15 discovery detectors (comparable-effort matching, robust z, bootstrap CI, Mann–Kendall) ─► ranking
  ─► GoldenCheetah adapter ─► AI commentary (validated) ─► post-discovery metrics ─► incremental baselines
```

| Piece | Where |
|---|---|
| Canonical telemetry, quality | `backend/athleteiq/ingestion/` |
| 305 registry + calculators | `backend/athleteiq/metrics/` · coverage in [docs/METRICS_COVERAGE.md](docs/METRICS_COVERAGE.md) |
| Indexes (formula in the module docstring) | `backend/athleteiq/indexes.py` |
| Discovery engine (plugins: `@register`) | `backend/athleteiq/discovery/` |
| Gemini tools + claim validation | `backend/athleteiq/ai/` |
| GoldenCheetah adapter | `backend/athleteiq/gc/adapter.py` |
| Tables + migration | `backend/athleteiq/models.py`, `backend/alembic/` |
| UI (Next.js + Tailwind + ECharts) | `frontend/app/page.tsx` |
| Plan and contracts | [docs/PLAN.md](docs/PLAN.md) |

## Honest status (hackathon cut)

* **Verified:** the full journey on Docker Compose (load the demo or upload a FIT over HTTP → worker → discoveries,
  charts, indexes, explorer, Ask). There are 58 backend tests. All 88 metrics marked `implemented_validated` are
  checked against analytic ground truth, and a test fails if one isn't.
* **Not verified:**
  * **Gemini:** no key was available. The tool loop is written against google-genai 1.x but has never called the
    real API. The fallback and the claim validator are tested.
  * **GoldenCheetah:** not installed here. The adapter follows its documented REST/CSV API and was not run against
    a real instance.
  * **Real device files:** none were on this machine. FIT parsing is tested with files from our own minimal FIT
    encoder, read by `fitdecode`.
* **Cut for time:**
  * MinIO: the image wasn't pullable here. The compose stack stores originals in a volume; the S3 code path exists
    (`STORAGE=s3`) but is untested.
  * No frontend component tests, no GoldenCheetah adapter test, and no Postgres-specific test suite. The compose
    run exercised Postgres end to end.
  * No auth; this is single-user.
* **Data:** the demo athlete is synthetic, generated and then run through the real pipeline. No discoveries are
  hard-coded.
* **Science:** the indexes are personal descriptors, not medical or physiological standards. There is no injury
  prediction: the risk metrics are load descriptors or are registered as pending.

Dependency licences: FastAPI, Pydantic, SQLAlchemy, Alembic, Polars, NumPy, SciPy, Next.js, React, Tailwind and
fitdecode are MIT/BSD/Apache; statsmodels is BSD-3; ECharts and Dramatiq are Apache-2.0 and LGPL-3.0; psycopg is
LGPL-3.0; gpxpy is Apache-2.0; google-genai is Apache-2.0.
