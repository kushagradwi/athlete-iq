"""Chart payloads for the frontend (ECharts). Series are downsampled to ≤ 1500 points by block mean."""
from __future__ import annotations

import numpy as np
from sqlalchemy import select

from . import models as m
from . import repo
from .metrics.calculators import PD_DURATIONS

MAX_POINTS = 1500


def _block(a: np.ndarray, k: int):
    if k <= 1:
        return a
    n = a.size // k * k
    with np.errstate(invalid="ignore"):
        return np.nanmean(a[:n].reshape(-1, k), axis=1) if n else a


def _list(a):
    return [None if not np.isfinite(v) else round(float(v), 3) for v in a]


def activity_charts(s, act: m.Activity) -> dict:
    rows = repo.samples(s, act.id)
    if not rows:
        return {}
    n = len(rows)
    k = max(1, int(np.ceil(n / MAX_POINTS)))

    def arr(attr):
        return np.array([np.nan if getattr(r, attr) is None else getattr(r, attr) for r in rows], float)

    t = np.arange(n, dtype=float)
    mv = np.array([r.moving for r in rows])
    sp = arr("speed_ms")
    sp30 = np.convolve(np.nan_to_num(sp), np.ones(30) / 30, mode="same")
    with np.errstate(divide="ignore", invalid="ignore"):
        pace = np.where(mv & (sp30 > 0.5), 1000 / sp30, np.nan)
    hr, cad, alt, dist = arr("heart_rate"), arr("cadence_spm"), arr("altitude_m"), arr("distance_m")
    series = {"t": _list(_block(t, k)), "distance_km": _list(_block(dist / 1000, k)), "pace_s_km": _list(_block(pace, k)),
              "heart_rate": _list(_block(hr, k)), "cadence": _list(_block(cad, k)), "altitude": _list(_block(alt, k)),
              "grade": _list(_block(arr("grade_pct"), k)), "power": _list(_block(arr("power_w"), k))}
    segs = s.scalars(select(m.EffortSegment).where(m.EffortSegment.activity_id == act.id).order_by(m.EffortSegment.start_s)).all()
    splits = [{"label": f"km {i + 1}", "seconds": x.duration_s, "avg_hr": x.avg_hr, "start_s": x.start_s,
               "segment_id": str(x.id)} for i, x in enumerate(z for z in segs if z.kind == "split_km")]
    intervals = [{"kind": x.kind, "start_s": x.start_s, "duration_s": x.duration_s, "pace_s_km": x.avg_pace_s_km,
                  "avg_hr": x.avg_hr, "segment_id": str(x.id)} for x in segs if x.kind in ("interval", "recovery")]
    th = (act.summary or {}).get("thresholds", {})
    lthr = th.get("lthr")
    hr_hist = pace_hist = None
    hm = hr[mv & np.isfinite(hr)]
    if hm.size > 60:
        edges = np.arange(np.floor(hm.min() / 5) * 5, np.ceil(hm.max() / 5) * 5 + 5, 5)
        c, _ = np.histogram(hm, edges)
        hr_hist = {"bins": edges[:-1].tolist(), "minutes": (c / 60).round(2).tolist(), "lthr": lthr}
    pm = pace[np.isfinite(pace)]
    if pm.size > 60:
        lo, hi = np.percentile(pm, 1), np.percentile(pm, 99)
        edges = np.arange(np.floor(lo / 10) * 10, np.ceil(hi / 10) * 10 + 10, 10)
        c, _ = np.histogram(np.clip(pm, edges[0], edges[-1] - 1e-6), edges)
        pace_hist = {"bins": edges[:-1].tolist(), "minutes": (c / 60).round(2).tolist()}
    return {"activity_id": str(act.id), "downsample_factor": k, "series": series, "km_splits": splits,
            "intervals": intervals, "hr_distribution": hr_hist, "pace_distribution": pace_hist,
            "pace_duration": pace_duration(s, act), "gaps": (act.summary or {}).get("gaps", [])}


def pace_duration(s, act):
    """This activity's best pace per duration vs the athlete's previous best (strictly earlier activities)."""
    cur = (act.summary or {}).get("pd_curve") or {}
    prior = {}
    for a in s.scalars(select(m.Activity).where(m.Activity.athlete_id == act.athlete_id, m.Activity.start_time < act.start_time,
                                                m.Activity.status == "analysed")):
        for k, v in ((a.summary or {}).get("pd_curve") or {}).items():
            prior[k] = max(prior.get(k, 0), v)
    rows = []
    for d in PD_DURATIONS:
        k = str(d)
        rows.append({"duration_s": d, "pace_s_km": round(1000 / cur[k], 1) if cur.get(k) else None,
                     "previous_best_pace_s_km": round(1000 / prior[k], 1) if prior.get(k) else None})
    return rows


def progression(s, athlete_id) -> dict:
    acts = s.scalars(select(m.Activity).where(m.Activity.athlete_id == athlete_id, m.Activity.status == "analysed")
                     .order_by(m.Activity.start_time)).all()
    ids = [a.id for a in acts]
    keys = ("running.efficiency_factor", "running.avg_pace", "running.aerobic_decoupling", "load.ctl", "load.atl",
            "load.tsb", "load.session_load", "running.cardiac_cost", "biomechanics.avg_cadence", "running.distance")
    vals = {}
    if ids:
        for aid, mid, v in s.execute(select(m.MetricResultRow.activity_id, m.MetricResultRow.metric_id, m.MetricResultRow.value)
                                     .where(m.MetricResultRow.activity_id.in_(ids), m.MetricResultRow.metric_id.in_(keys),
                                            m.MetricResultRow.state.in_(repo.USABLE))):
            vals.setdefault(aid, {})[mid] = v
    idx = {}
    if ids:
        for r in s.scalars(select(m.AthleteIndex).where(m.AthleteIndex.activity_id.in_(ids))):
            idx.setdefault(r.activity_id, {})[r.index_id] = r.score
    base = s.scalar(select(m.AthleteBaseline).where(m.AthleteBaseline.athlete_id == athlete_id,
                                                    m.AthleteBaseline.key == "curve:pace_duration_best"))
    return {"athlete_id": str(athlete_id),
            "activities": [{"activity_id": str(a.id), "date": a.start_time.isoformat(), "distance_m": a.distance_m,
                            "metrics": vals.get(a.id, {}), "indexes": idx.get(a.id, {})} for a in acts],
            "pace_duration_best": (base.data if base else {})}
