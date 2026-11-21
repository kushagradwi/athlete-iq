"""Evidence tools. The AI can only see what these return; every object carries an id it must cite."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import desc, select

from .. import models as m
from ..metrics.registry import load_all

TOOL_SPECS = [
    ("get_activity_metrics", "Metric results for one activity (value, unit, state). Optional category filter.",
     {"activity_id": "string", "category": "string"}, ["activity_id"]),
    ("get_activity_charts", "Chart summaries for one activity: km splits (pace, HR), HR zone minutes, intervals.",
     {"activity_id": "string"}, ["activity_id"]),
    ("get_historical_comparisons", "Chronological values of one metric across the athlete's activities.",
     {"metric_id": "string", "limit": "integer"}, ["metric_id"]),
    ("get_personal_records", "Best pace for durations, fastest distances, longest holds per pace band.", {}, []),
    ("get_discoveries", "Ranked evidence-backed discoveries; optionally for one activity.",
     {"activity_id": "string", "limit": "integer"}, []),
    ("get_performance_indexes", "The five performance indexes for an activity (or the latest).",
     {"activity_id": "string"}, []),
    ("get_training_history", "Activities in the last N days with key metrics.", {"days": "integer"}, []),
]


def json_schema(props, required):
    return {"type": "object", "properties": {k: {"type": v} for k, v in props.items()}, "required": required}


def _uuid(x):
    try:
        return uuid.UUID(str(x))
    except (ValueError, TypeError):
        return None


class Tools:
    def __init__(self, s, athlete_id):
        self.s, self.athlete_id = s, athlete_id
        self.reg = load_all()

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name not in {t[0] for t in TOOL_SPECS}:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}

    def _activity(self, activity_id):
        a = self.s.get(m.Activity, _uuid(activity_id)) if activity_id else None
        if a is None or a.athlete_id != self.athlete_id:
            return None
        return a

    def _latest(self):
        return self.s.scalar(select(m.Activity).where(m.Activity.athlete_id == self.athlete_id,
                                                      m.Activity.status == "analysed").order_by(desc(m.Activity.start_time)))

    def get_activity_metrics(self, activity_id, category=None):
        a = self._activity(activity_id)
        if not a:
            return {"error": "activity not found"}
        rows = self.s.scalars(select(m.MetricResultRow).where(m.MetricResultRow.activity_id == a.id)).all()
        out = []
        for r in rows:
            d = self.reg.get(r.metric_id)
            if category and d and d.category != category:
                continue
            if r.state in ("CALCULATED", "ESTIMATED"):
                out.append({"metric_id": r.metric_id, "name": d.name if d else r.metric_id, "value": round(r.value, 4),
                            "unit": r.unit, "state": r.state})
        return {"activity_id": str(a.id), "date": a.start_time.isoformat(), "metrics": out}

    def get_activity_charts(self, activity_id):
        a = self._activity(activity_id)
        if not a:
            return {"error": "activity not found"}
        segs = self.s.scalars(select(m.EffortSegment).where(m.EffortSegment.activity_id == a.id)
                              .order_by(m.EffortSegment.start_s)).all()
        zones = {r.metric_id: r.value for r in self.s.scalars(select(m.MetricResultRow).where(
            m.MetricResultRow.activity_id == a.id, m.MetricResultRow.metric_id.like("running.time_hr_z%")))}
        return {"activity_id": str(a.id),
                "km_splits": [{"segment_id": str(x.id), "km": i + 1, "seconds": x.duration_s,
                               "avg_hr": round(x.avg_hr, 1) if x.avg_hr else None}
                              for i, x in enumerate(s for s in segs if s.kind == "split_km")],
                "intervals": [{"segment_id": str(x.id), "duration_s": x.duration_s,
                               "pace_s_km": round(x.avg_pace_s_km, 1) if x.avg_pace_s_km else None,
                               "avg_hr": round(x.avg_hr, 1) if x.avg_hr else None} for x in segs if x.kind == "interval"],
                "hr_zone_minutes": {k.split("_")[-1]: round(v / 60, 1) for k, v in zones.items() if v is not None}}

    def get_historical_comparisons(self, metric_id, limit=30):
        rows = self.s.execute(select(m.Activity.id, m.Activity.start_time, m.MetricResultRow.value)
                              .join(m.MetricResultRow, m.MetricResultRow.activity_id == m.Activity.id)
                              .where(m.Activity.athlete_id == self.athlete_id, m.MetricResultRow.metric_id == metric_id,
                                     m.MetricResultRow.state.in_(("CALCULATED", "ESTIMATED")))
                              .order_by(desc(m.Activity.start_time)).limit(int(limit or 30))).all()
        d = self.reg.get(metric_id)
        return {"metric_id": metric_id, "unit": d.unit if d else None,
                "values": [{"activity_id": str(i), "date": t.isoformat(), "value": round(v, 4)} for i, t, v in reversed(rows)]}

    def get_personal_records(self):
        base = self.s.scalar(select(m.AthleteBaseline).where(m.AthleteBaseline.athlete_id == self.athlete_id,
                                                             m.AthleteBaseline.key == "curve:pace_duration_best"))
        pd = {k: {"pace_s_km": round(1000 / v["speed_ms"], 1), "activity_id": v["activity_id"], "date": v["date"]}
              for k, v in ((base.data if base else {}) or {}).items()}
        dist = {}
        for mid in ("running.best_1km", "running.best_5km", "running.best_10km"):
            r = self.s.execute(select(m.MetricResultRow.activity_id, m.MetricResultRow.value)
                               .where(m.MetricResultRow.athlete_id == self.athlete_id, m.MetricResultRow.metric_id == mid,
                                      m.MetricResultRow.state == "CALCULATED").order_by(m.MetricResultRow.value)).first()
            if r:
                dist[mid] = {"seconds": r[1], "activity_id": str(r[0])}
        holds = {}
        for a in self.s.scalars(select(m.Activity).where(m.Activity.athlete_id == self.athlete_id,
                                                         m.Activity.status == "analysed")):
            for band, h in ((a.summary or {}).get("holds") or {}).items():
                if h["seconds"] > holds.get(band, {}).get("seconds", 0):
                    holds[band] = {"seconds": h["seconds"], "avg_hr": h.get("avg_hr"), "activity_id": str(a.id),
                                   "date": a.start_time.isoformat(), "band_s_km": [int(band), int(band) + 10]}
        return {"pace_duration_best": pd, "fastest_distances": dist, "longest_holds_by_pace_band": holds}

    def get_discoveries(self, activity_id=None, limit=10):
        q = select(m.Discovery).where(m.Discovery.athlete_id == self.athlete_id)
        if activity_id:
            q = q.where(m.Discovery.activity_id == _uuid(activity_id))
        rows = self.s.scalars(q.order_by(desc(m.Discovery.created_at), desc(m.Discovery.significance_score))
                              .limit(int(limit or 10))).all()
        return {"discoveries": [discovery_json(d, evidence=True) for d in rows]}

    def get_performance_indexes(self, activity_id=None):
        a = self._activity(activity_id) if activity_id else self._latest()
        if not a:
            return {"error": "no analysed activity"}
        rows = self.s.scalars(select(m.AthleteIndex).where(m.AthleteIndex.activity_id == a.id)).all()
        return {"activity_id": str(a.id), "indexes": [{"index_id": r.index_id, "score": r.score, "state": r.state,
                                                       "confidence": r.confidence} for r in rows]}

    def get_training_history(self, days=90):
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days or 90))
        acts = self.s.scalars(select(m.Activity).where(m.Activity.athlete_id == self.athlete_id,
                                                       m.Activity.status == "analysed", m.Activity.start_time >= since)
                              .order_by(m.Activity.start_time)).all()
        keys = ("running.avg_pace", "running.avg_heart_rate", "running.efficiency_factor", "load.session_load",
                "running.km_split_cv", "running.aerobic_decoupling")
        vals = {}
        if acts:
            for aid, mid, v in self.s.execute(select(m.MetricResultRow.activity_id, m.MetricResultRow.metric_id,
                                                     m.MetricResultRow.value).where(
                    m.MetricResultRow.activity_id.in_([a.id for a in acts]), m.MetricResultRow.metric_id.in_(keys),
                    m.MetricResultRow.state.in_(("CALCULATED", "ESTIMATED")))):
                vals.setdefault(aid, {})[mid] = round(v, 4)
        return {"days": days, "activities": [{"activity_id": str(a.id), "date": a.start_time.isoformat(), "sport": a.sport,
                                              "distance_m": round(a.distance_m or 0, 1), "moving_s": a.moving_s,
                                              "metrics": vals.get(a.id, {})} for a in acts]}


def discovery_json(d: m.Discovery, evidence=False) -> dict:
    out = {"discovery_id": str(d.id), "activity_id": str(d.activity_id), "athlete_id": str(d.athlete_id), "type": d.type,
           "classification": d.classification, "title": d.title, "description": d.description,
           "observed_value": {k: v for k, v in (d.observed_value or {}).items() if not k.startswith("_")},
           "baseline_value": d.baseline_value, "improvement": d.improvement, "confidence": d.confidence,
           "significance_score": d.significance_score, "ranking": d.ranking, "limitations": d.limitations,
           "recommended_experiment": d.recommended_experiment, "algorithm_version": d.algorithm_version,
           "created_at": d.created_at.isoformat() if d.created_at else None}
    if evidence:
        out["evidence"] = [{"kind": e.kind, "ref_id": e.ref_id, "label": e.label, "value": e.value, "unit": e.unit,
                            "detail": e.detail} for e in d.evidence]
    return out
