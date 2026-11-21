"""Upload → analysis job. Idempotent per (athlete, file hash); retries resume from scratch safely."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import uuid

from sqlalchemy import delete, select

from . import indexes as idx
from . import models as m
from . import repo, segments, storage, thresholds
from .config import settings
from .discovery import engine as disc_engine
from .discovery.base import DetectorContext
from .discovery.detectors import aerobic_longest
from .gc import adapter as gc
from .ingestion import parsers
from .ingestion.normalize import normalize
from .metrics import calculators as C
from .metrics import engine as metric_engine
from .metrics.context import Ctx

log = logging.getLogger("athleteiq.pipeline")


class UploadError(ValueError):
    pass


def submit(s, athlete_id: uuid.UUID, filename: str, data: bytes) -> tuple[m.AnalysisJob, bool]:
    """Validate and store the original file, create (or return the existing) job. Returns (job, created)."""
    if len(data) > settings().max_upload_mb * 1024 * 1024:
        raise UploadError(f"file larger than {settings().max_upload_mb} MB")
    if not data:
        raise UploadError("empty file")
    try:
        fmt = parsers.detect_format(filename, data[:4096])
    except parsers.ParseError as e:
        raise UploadError(str(e)) from e
    sha = hashlib.sha256(data).hexdigest()
    existing = s.scalar(select(m.AnalysisJob).where(m.AnalysisJob.athlete_id == athlete_id,
                                                    m.AnalysisJob.file_sha256 == sha,
                                                    m.AnalysisJob.status != "failed"))
    if existing:
        return existing, False
    key = f"raw/{athlete_id}/{sha}.{fmt}"
    storage.put(key, data)
    job = m.AnalysisJob(athlete_id=athlete_id, original_filename=os.path.basename(filename)[:255], file_sha256=sha,
                        storage_key=key, status="queued", stage="queued")
    s.add(job)
    s.flush()
    return job, True


def _stage(s, job, stage, progress):
    job.stage, job.progress = stage, progress
    s.commit()


def run_job(job_id) -> None:
    """Executes a job in its own session. Safe to call again after a failure."""
    from .db import session
    with session() as s:
        job = s.get(m.AnalysisJob, uuid.UUID(str(job_id)))
        if job is None or job.status == "done":
            return
        job.status, job.attempts, job.error = "running", job.attempts + 1, None
        s.commit()
        try:
            _analyse(s, job)
            job.status, job.stage, job.progress = "done", "done", 1.0
        except Exception as e:
            log.exception("analysis failed")
            s.rollback()
            job = s.get(m.AnalysisJob, uuid.UUID(str(job_id)))
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            if job.activity_id:
                act = s.get(m.Activity, job.activity_id)
                if act:
                    act.status = "failed"
        s.commit()


def _analyse(s, job: m.AnalysisJob):
    athlete = s.get(m.Athlete, job.athlete_id)
    data = storage.get(job.storage_key)
    _stage(s, job, "parsing", 0.05)
    raw = parsers.parse(job.original_filename, data)
    _stage(s, job, "normalizing", 0.15)
    t = normalize(raw)
    if t.moving_s < 60:
        raise parsers.ParseError("less than 60 s of movement detected")

    act = s.scalar(select(m.Activity).where(m.Activity.athlete_id == athlete.id, m.Activity.file_sha256 == job.file_sha256))
    if act is None:
        act = m.Activity(athlete_id=athlete.id, file_sha256=job.file_sha256)
        s.add(act)
    act.sport, act.sub_sport, act.start_time = t.sport, raw.sub_sport, t.start_time
    act.elapsed_s, act.moving_s, act.distance_m = t.n, t.moving_s, t.distance_m
    act.source_format, act.original_filename, act.storage_key = raw.fmt, job.original_filename, job.storage_key
    act.device, act.channel_provenance, act.quality = t.device, t.provenance, _json(t.quality)
    act.status = "pending"
    s.flush()
    job.activity_id = act.id
    for tbl in (m.MetricResultRow, m.EffortSegment, m.AthleteIndex, m.Discovery, m.GoldenCheetahSync):
        s.execute(delete(tbl).where(tbl.activity_id == act.id))  # idempotent re-run
    _stage(s, job, "storing telemetry", 0.25)
    repo.save_samples(s, act.id, t)

    _stage(s, job, "metrics", 0.4)
    history = repo.load_history(s, athlete.id, t.start_time, exclude=act.id)
    th = thresholds.resolve(athlete, t, history)
    ctx = Ctx(t=t, th=th, history=history)
    results = metric_engine.run(ctx, "main")
    values = {k: r.value for k, r in results.items() if r.state in repo.USABLE}

    _stage(s, job, "segments", 0.5)
    segs = C.splits(ctx) + C.steadies(ctx)
    work, rest = C.reps(ctx)
    segs += work + rest
    for sg in segs:
        s.add(m.EffortSegment(athlete_id=athlete.id, activity_id=act.id, kind=sg.kind, start_s=sg.start_s,
                              duration_s=sg.duration_s, distance_m=sg.distance_m, avg_pace_s_km=sg.avg_pace_s_km,
                              avg_hr=sg.avg_hr, avg_cadence=sg.avg_cadence, avg_grade=sg.avg_grade,
                              elev_gain_m=sg.elev_gain_m, temperature_c=sg.temperature_c, pace_cv=sg.pace_cv,
                              quality=sg.quality, start_lat=sg.start_lat, start_lon=sg.start_lon, end_lat=sg.end_lat,
                              end_lon=sg.end_lon, started_at=t.start_time + dt.timedelta(seconds=sg.start_s)))

    _stage(s, job, "indexes", 0.6)
    index_out = idx.compute(ctx, values)
    ctx.cache["indexes"] = {k: v["score"] for k, v in index_out.items()}
    for iid, v in index_out.items():
        s.add(m.AthleteIndex(athlete_id=athlete.id, activity_id=act.id, index_id=iid, score=v["score"], state=v["state"],
                             confidence=v["confidence"], components=_json(v), version=v["version"]))

    _stage(s, job, "discoveries", 0.7)
    recent = s.scalars(select(m.Discovery).where(m.Discovery.athlete_id == athlete.id,
                                                 m.Discovery.created_at >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14))).all()
    dctx = DetectorContext(m=ctx, metrics=values, segments=segs, athlete_goal=athlete.goal or "general",
                           recent_keys={(d.observed_value or {}).get("_dedupe_key") for d in recent})
    dres = disc_engine.run(dctx)
    for c in dres["discoveries"]:
        row = m.Discovery(id=uuid.UUID(c.discovery_id), athlete_id=athlete.id, activity_id=act.id, type=c.type,
                          classification=c.classification, title=c.title, description=c.description,
                          observed_value=_json({**c.observed_value, "_dedupe_key": c.dedupe_key}),
                          baseline_value=_json(c.baseline_value), improvement=_json(c.improvement),
                          confidence=c.confidence, significance_score=c.significance_score, ranking=_json(c.ranking),
                          limitations=c.limitations, recommended_experiment=_json(c.recommended_experiment),
                          algorithm_version=c.algorithm_version)
        row.evidence = [m.DiscoveryEvidence(kind=e.kind, ref_id=e.ref_id, label=e.label[:200], value=_num(e.value),
                                            unit=e.unit, detail=_json(e.detail)) for e in c.evidence]
        s.add(row)

    ctx.cache["discovery_summary"] = {
        "discoveries": [{"classification": c.classification, "significance_score": c.significance_score,
                         "confidence": c.confidence, "ranking": c.ranking, "evidence": c.evidence}
                        for c in dres["discoveries"]],
        "detectors_run": dres["detectors_run"], "detectors_abstained": len(dres["abstained"]),
        "comparable_matches": dres["comparable_matches"], "match_quality": dres["match_quality"]}

    _stage(s, job, "goldencheetah", 0.8)
    g = gc.sync(job.original_filename, data, t.start_time, values)
    s.add(m.GoldenCheetahSync(activity_id=act.id, status=g["status"], gc_filename=g["gc_filename"],
                              gc_metrics=_json(g["gc_metrics"]), comparison=_json(g["comparison"]), message=g["message"]))
    # GC values live in golden_cheetah_sync (with provenance); our metric results stay authoritative.

    _stage(s, job, "ai commentary", 0.85)
    summary = {"pd_curve": C.pd_curve(ctx) if t.has("speed_ms") else {}, "holds": C.hold_bands(ctx),
               "indexes": ctx.cache["indexes"], "abstained": dres["abstained"], "detector_errors": dres["errors"],
               "thresholds": {"max_hr": th.max_hr, "rest_hr": th.rest_hr, "lthr": th.lthr,
                              "threshold_pace_s_km": th.threshold_pace_s_km, "ftp_w": th.ftp_w,
                              "weight_kg": th.weight_kg, "estimated": sorted(th.estimated)},
               "gaps": t.gaps, "notes": raw.notes}
    if t.has("heart_rate"):
        summary["aerobic_longest"] = aerobic_longest(ctx)[0]
    act.summary = _json(summary)
    act.status = "analysed"
    s.flush()
    try:
        from .ai import service as ai
        with s.begin_nested():  # savepoint: an AI failure must not roll back the analysis
            ctx.cache["ai_validation"] = ai.commentary(s, athlete.id, act.id)
    except Exception as e:  # AI is optional; analysis stands without it
        log.warning("AI commentary failed: %s", e)

    _stage(s, job, "final metrics", 0.95)
    results.update(metric_engine.run(ctx, "post"))
    for r in results.values():
        s.add(m.MetricResultRow(activity_id=act.id, athlete_id=athlete.id, metric_id=r.metric_id, value=r.value,
                                unit=r.unit, state=r.state, source=r.source, quality=r.quality, detail=_json(r.detail),
                                algorithm_version=r.algorithm_version))
    values = {k: r.value for k, r in results.items() if r.state in repo.USABLE}
    repo.update_baselines(s, athlete.id, act, values, summary)
    s.flush()


def _num(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _json(o):
    from .metrics.engine import _clean
    if hasattr(o, "__dict__") and not isinstance(o, dict):
        o = o.__dict__
    return _clean(o)
