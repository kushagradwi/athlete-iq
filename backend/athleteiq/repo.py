"""Database reads/writes shared by the pipeline, API and AI tools."""
from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from . import models as m
from .metrics.context import PriorActivity
from .metrics.registry import load_all

USABLE = ("CALCULATED", "ESTIMATED")


def sync_registry(s: Session):
    reg = load_all()
    existing = {r.metric_id: r for r in s.scalars(select(m.MetricDefinitionRow))}
    for d in reg.values():
        row = existing.get(d.metric_id) or m.MetricDefinitionRow(metric_id=d.metric_id)
        row.name, row.category, row.sport, row.unit = d.name, d.category, d.sport, d.unit
        row.status, row.algorithm_version, row.definition = d.status, d.algorithm_version, d.to_dict()
        s.add(row)
    s.flush()


def load_history(s: Session, athlete_id, before: dt.datetime, exclude=None) -> list[PriorActivity]:
    acts = s.scalars(select(m.Activity).where(m.Activity.athlete_id == athlete_id, m.Activity.start_time < before,
                                              m.Activity.status == "analysed").order_by(m.Activity.start_time)).all()
    acts = [a for a in acts if a.id != exclude]
    if not acts:
        return []
    ids = [a.id for a in acts]
    metrics: dict = {i: {} for i in ids}
    for aid, mid, v in s.execute(select(m.MetricResultRow.activity_id, m.MetricResultRow.metric_id, m.MetricResultRow.value)
                                 .where(m.MetricResultRow.activity_id.in_(ids), m.MetricResultRow.state.in_(USABLE))):
        metrics[aid][mid] = v
    segs: dict = {i: [] for i in ids}
    for row in s.scalars(select(m.EffortSegment).where(m.EffortSegment.activity_id.in_(ids))):
        segs[row.activity_id].append(segment_to_dict(row))
    return [PriorActivity(str(a.id), _aware(a.start_time), a.sport, a.distance_m or 0.0, a.moving_s, metrics[a.id],
                          a.summary or {}, segs[a.id]) for a in acts]


def _aware(t):
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def segment_to_dict(r: m.EffortSegment) -> dict:
    return {"id": str(r.id), "kind": r.kind, "start_s": r.start_s, "duration_s": r.duration_s, "distance_m": r.distance_m,
            "avg_pace_s_km": r.avg_pace_s_km, "avg_hr": r.avg_hr, "avg_cadence": r.avg_cadence, "avg_grade": r.avg_grade,
            "elev_gain_m": r.elev_gain_m, "temperature_c": r.temperature_c, "pace_cv": r.pace_cv, "quality": r.quality,
            "start_lat": r.start_lat, "start_lon": r.start_lon, "end_lat": r.end_lat, "end_lon": r.end_lon}


def save_samples(s: Session, activity_id, t):
    s.execute(delete(m.TelemetrySample).where(m.TelemetrySample.activity_id == activity_id))
    cols = {"distance_m": "distance_m", "lat": "lat", "lon": "lon", "altitude_m": "altitude_m", "speed_ms": "speed_ms",
            "heart_rate": "heart_rate", "cadence_spm": "cadence_spm", "power_w": "power_w", "temperature_c": "temperature_c",
            "grade_pct": "grade_pct", "vertical_oscillation_mm": "vertical_oscillation_mm",
            "ground_contact_ms": "ground_contact_ms", "stride_length_m": "stride_length_m",
            "respiration_rate": "respiration_rate"}
    arrays = {k: t.ch[v] for k, v in cols.items()}
    rows = []
    for i in range(t.n):
        r = {"activity_id": activity_id, "elapsed_s": i, "moving": bool(t.moving[i])}
        for k, a in arrays.items():
            v = a[i]
            r[k] = float(v) if np.isfinite(v) else None
        rows.append(r)
    for k in range(0, len(rows), 5000):  # chunked inserts
        s.execute(insert(m.TelemetrySample), rows[k:k + 5000])


def samples(s: Session, activity_id) -> list[m.TelemetrySample]:
    return s.scalars(select(m.TelemetrySample).where(m.TelemetrySample.activity_id == activity_id)
                     .order_by(m.TelemetrySample.elapsed_s)).all()


def metric_results(s: Session, activity_id) -> list[m.MetricResultRow]:
    return s.scalars(select(m.MetricResultRow).where(m.MetricResultRow.activity_id == activity_id)).all()


def update_baselines(s: Session, athlete_id, activity, metric_values: dict, summary: dict):
    """Incremental aggregates: best pace-duration curve and capped value histories for key metrics."""
    def get(key):
        row = s.scalar(select(m.AthleteBaseline).where(m.AthleteBaseline.athlete_id == athlete_id,
                                                        m.AthleteBaseline.key == key))
        if row is None:
            row = m.AthleteBaseline(athlete_id=athlete_id, key=key, data={})
            s.add(row)
        return row

    row = get("curve:pace_duration_best")
    d = dict(row.data or {})
    for k, v in (summary.get("pd_curve") or {}).items():
        if v > d.get(k, {}).get("speed_ms", 0):
            d[k] = {"speed_ms": v, "activity_id": str(activity.id), "date": activity.start_time.isoformat()}
    row.data = d
    for mid in ("running.efficiency_factor", "running.aerobic_decoupling", "running.avg_pace", "running.cardiac_cost",
                "biomechanics.avg_cadence", "load.session_load", "running.km_split_cv", "running.distance"):
        v = metric_values.get(mid)
        if v is None:
            continue
        row = get(f"metric:{mid}")
        pts = [p for p in (row.data or {}).get("points", []) if p["activity_id"] != str(activity.id)]
        pts.append({"date": activity.start_time.isoformat(), "value": v, "activity_id": str(activity.id)})
        pts.sort(key=lambda p: p["date"])
        row.data = {"points": pts[-200:]}


def new_id():
    return uuid.uuid4()
