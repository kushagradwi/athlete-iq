"""ATHLETE IQ REST API (v1). OpenAPI docs at /docs."""
from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import charts, models as m, repo
from ..ai import service as ai
from ..ai.tools import discovery_json
from ..config import settings
from ..db import get_session, session
from ..metrics.registry import CATEGORIES, coverage, load_all
from ..pipeline import UploadError, submit
from ..worker import enqueue

app = FastAPI(title="ATHLETE IQ API", version="1.0.0",
              description="Upload workouts, get 305-metric analysis, evidence-backed discoveries and AI explanations.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings().cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    from .. import storage
    storage.ensure_bucket()
    with session() as s:
        repo.sync_registry(s)


def _uuid(x, what="id"):
    try:
        return uuid.UUID(str(x))
    except ValueError:
        raise HTTPException(422, f"invalid {what}")


def _athlete(s, athlete_id):
    a = s.get(m.Athlete, _uuid(athlete_id, "athlete_id"))
    if not a:
        raise HTTPException(404, "athlete not found")
    return a


def _activity(s, activity_id):
    a = s.get(m.Activity, _uuid(activity_id, "activity_id"))
    if not a:
        raise HTTPException(404, "activity not found")
    return a


# ------------------------------------------------------------------ athletes
class AthleteIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    birth_year: int | None = Field(None, ge=1900, le=2030)
    sex: str | None = None
    max_hr: float | None = Field(None, ge=120, le=240)
    rest_hr: float | None = Field(None, ge=25, le=120)
    lthr: float | None = Field(None, ge=100, le=230)
    threshold_pace_s_km: float | None = Field(None, ge=150, le=900)
    ftp_w: float | None = Field(None, ge=50, le=600)
    weight_kg: float | None = Field(None, ge=25, le=250)
    goal: str = "general"


def athlete_json(a):
    return {k: getattr(a, k) for k in ("name", "birth_year", "sex", "max_hr", "rest_hr", "lthr", "threshold_pace_s_km",
                                       "ftp_w", "weight_kg", "goal", "is_demo")} | {"athlete_id": str(a.id)}


@app.get("/api/v1/athletes", tags=["athletes"])
def list_athletes(s: Session = Depends(get_session)):
    return [athlete_json(a) for a in s.scalars(select(m.Athlete).order_by(m.Athlete.created_at))]


@app.post("/api/v1/athletes", tags=["athletes"], status_code=201)
def create_athlete(body: AthleteIn, s: Session = Depends(get_session)):
    a = m.Athlete(**body.model_dump())
    s.add(a)
    s.flush()
    return athlete_json(a)


@app.patch("/api/v1/athletes/{athlete_id}", tags=["athletes"])
def update_athlete(athlete_id: str, body: AthleteIn, s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    return athlete_json(a)


@app.post("/api/v1/demo", tags=["athletes"], status_code=202)
def create_demo(s: Session = Depends(get_session)):
    """Creates the synthetic demo athlete and queues 12 weeks of generated workouts through the real pipeline."""
    from ..demo import seed
    a = seed(s)
    return athlete_json(a)


# ------------------------------------------------------------------ upload & jobs
@app.post("/api/v1/activities/upload", tags=["activities"], status_code=202)
async def upload(athlete_id: str = Form(...), file: UploadFile = File(...), s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    data = await file.read()
    try:
        job, created = submit(s, a.id, file.filename or "upload", data)
    except UploadError as e:
        raise HTTPException(422, str(e))
    s.commit()
    if created:
        enqueue(job.id)
        s.refresh(job)
    return job_json(job) | {"duplicate": not created}


def job_json(j):
    return {"job_id": str(j.id), "status": j.status, "stage": j.stage, "progress": j.progress, "error": j.error,
            "activity_id": str(j.activity_id) if j.activity_id else None, "filename": j.original_filename,
            "attempts": j.attempts}


@app.get("/api/v1/analysis/{job_id}", tags=["activities"])
def job_status(job_id: str, s: Session = Depends(get_session)):
    j = s.get(m.AnalysisJob, _uuid(job_id, "job_id"))
    if not j:
        raise HTTPException(404, "job not found")
    return job_json(j)


@app.post("/api/v1/analysis/{job_id}/retry", tags=["activities"], status_code=202)
def retry(job_id: str, s: Session = Depends(get_session)):
    j = s.get(m.AnalysisJob, _uuid(job_id, "job_id"))
    if not j:
        raise HTTPException(404, "job not found")
    if j.status != "failed":
        raise HTTPException(409, "only failed jobs can be retried")
    j.status, j.stage = "queued", "queued"
    s.commit()
    enqueue(j.id)
    return job_json(j)


@app.get("/api/v1/athletes/{athlete_id}/jobs", tags=["activities"])
def athlete_jobs(athlete_id: str, s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    rows = s.scalars(select(m.AnalysisJob).where(m.AnalysisJob.athlete_id == a.id).order_by(desc(m.AnalysisJob.created_at))
                     .limit(100)).all()
    return [job_json(j) for j in rows]


# ------------------------------------------------------------------ activities
def activity_json(a: m.Activity, s=None):
    out = {"activity_id": str(a.id), "athlete_id": str(a.athlete_id), "sport": a.sport, "sub_sport": a.sub_sport,
           "start_time": a.start_time.isoformat(), "elapsed_s": a.elapsed_s, "moving_s": a.moving_s,
           "distance_m": a.distance_m, "source_format": a.source_format, "original_filename": a.original_filename,
           "device": a.device, "status": a.status, "quality": a.quality, "channel_provenance": a.channel_provenance}
    if s is not None:
        keys = ("running.avg_pace", "running.avg_heart_rate", "load.energy_kcal", "environment.elevation_gain",
                "running.efficiency_factor", "load.session_load")
        vals = {r.metric_id: {"value": r.value, "state": r.state, "unit": r.unit}
                for r in s.scalars(select(m.MetricResultRow).where(m.MetricResultRow.activity_id == a.id,
                                                                   m.MetricResultRow.metric_id.in_(keys)))}
        out["overview"] = vals
        out["thresholds"] = (a.summary or {}).get("thresholds")
        out["notes"] = (a.summary or {}).get("notes", [])
        gcs = s.scalar(select(m.GoldenCheetahSync).where(m.GoldenCheetahSync.activity_id == a.id))
        out["goldencheetah"] = ({"status": gcs.status, "message": gcs.message, "comparison": gcs.comparison,
                                 "gc_filename": gcs.gc_filename} if gcs else None)
    return out


@app.get("/api/v1/athletes/{athlete_id}/activities", tags=["activities"])
def list_activities(athlete_id: str, s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    rows = s.scalars(select(m.Activity).where(m.Activity.athlete_id == a.id).order_by(desc(m.Activity.start_time))).all()
    counts = dict(s.execute(select(m.Discovery.activity_id, func.count()).where(m.Discovery.athlete_id == a.id)
                            .group_by(m.Discovery.activity_id)).all())
    return [activity_json(x) | {"discoveries": counts.get(x.id, 0)} for x in rows]


@app.get("/api/v1/activities/{activity_id}", tags=["activities"])
def get_activity(activity_id: str, s: Session = Depends(get_session)):
    return activity_json(_activity(s, activity_id), s)


@app.get("/api/v1/activities/{activity_id}/metrics", tags=["metrics"])
def activity_metrics(activity_id: str, category: str | None = None, s: Session = Depends(get_session)):
    a = _activity(s, activity_id)
    reg = load_all()
    res = {r.metric_id: r for r in repo.metric_results(s, a.id)}
    out = []
    for d in reg.values():
        if category and d.category != category:
            continue
        r = res.get(d.metric_id)
        out.append({"metric_id": d.metric_id, "name": d.name, "category": d.category, "unit": d.unit, "status": d.status,
                    "value": r.value if r else None,
                    "state": r.state if r else ("NOT_APPLICABLE" if d.implemented else "NOT_IMPLEMENTED"),
                    "quality": r.quality if r else None, "detail": r.detail if r else {},
                    "algorithm_version": d.algorithm_version})
    return {"activity_id": str(a.id), "metrics": out}


@app.get("/api/v1/activities/{activity_id}/charts", tags=["activities"])
def activity_charts(activity_id: str, s: Session = Depends(get_session)):
    return charts.activity_charts(s, _activity(s, activity_id))


@app.get("/api/v1/activities/{activity_id}/discoveries", tags=["discoveries"])
def activity_discoveries(activity_id: str, s: Session = Depends(get_session)):
    a = _activity(s, activity_id)
    rows = s.scalars(select(m.Discovery).where(m.Discovery.activity_id == a.id)
                     .order_by(desc(m.Discovery.significance_score))).all()
    c = ai.latest_commentary(s, a.id)
    return {"activity_id": str(a.id), "top": [discovery_json(d, evidence=True) for d in rows[:5]],
            "more": [discovery_json(d, evidence=True) for d in rows[5:]],
            "abstained": (a.summary or {}).get("abstained", []),
            "commentary": c.response if c else None}


@app.get("/api/v1/activities/{activity_id}/indexes", tags=["indexes"])
def activity_indexes(activity_id: str, s: Session = Depends(get_session)):
    a = _activity(s, activity_id)
    return [r.components for r in s.scalars(select(m.AthleteIndex).where(m.AthleteIndex.activity_id == a.id))]


# ------------------------------------------------------------------ athlete intelligence
@app.get("/api/v1/athletes/{athlete_id}/progression", tags=["athletes"])
def athlete_progression(athlete_id: str, s: Session = Depends(get_session)):
    return charts.progression(s, _athlete(s, athlete_id).id)


@app.get("/api/v1/athletes/{athlete_id}/indexes", tags=["indexes"])
def athlete_indexes(athlete_id: str, s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    latest = s.scalar(select(m.Activity).where(m.Activity.athlete_id == a.id, m.Activity.status == "analysed")
                      .order_by(desc(m.Activity.start_time)))
    if not latest:
        return {"athlete_id": str(a.id), "activity_id": None, "indexes": []}
    rows = s.scalars(select(m.AthleteIndex).where(m.AthleteIndex.activity_id == latest.id)).all()
    return {"athlete_id": str(a.id), "activity_id": str(latest.id), "indexes": [r.components for r in rows]}


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    activity_id: str | None = None


@app.post("/api/v1/athletes/{athlete_id}/ask", tags=["ai"])
def ask(athlete_id: str, body: AskIn, s: Session = Depends(get_session)):
    a = _athlete(s, athlete_id)
    act = _activity(s, body.activity_id).id if body.activity_id else None
    return ai.ask(s, a.id, body.question, act)


# ------------------------------------------------------------------ registry
@app.get("/api/v1/metrics/registry", tags=["metrics"])
def registry(category: str | None = Query(None), status: str | None = Query(None), q: str | None = Query(None)):
    out = []
    for d in load_all().values():
        if category and d.category != category or status and d.status != status:
            continue
        if q and q.lower() not in (d.metric_id + d.name + d.description).lower():
            continue
        out.append(d.to_dict())
    return {"total": len(load_all()), "count": len(out), "categories": {k: v[0] for k, v in CATEGORIES.items()},
            "metrics": out}


@app.get("/api/v1/metrics/coverage", tags=["metrics"])
def metrics_coverage():
    return coverage()


@app.get("/api/v1/health", tags=["system"])
def health(s: Session = Depends(get_session)):
    from ..gc.adapter import GoldenCheetah
    s.execute(select(1))
    return {"status": "ok", "job_mode": settings().job_mode, "storage": settings().storage,
            "ai": "gemini" if settings().gemini_api_key else "deterministic-fallback",
            "goldencheetah": "available" if GoldenCheetah().available() else "unavailable"}
