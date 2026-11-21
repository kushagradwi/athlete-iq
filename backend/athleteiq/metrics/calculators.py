"""Metric calculators. Each takes a Ctx and returns Out or raises NA.

Formulas are documented on the registry definitions; this file is the implementation."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
from scipy import stats as sps

from .. import segments as segmod
from ..ingestion.normalize import rolling_nanmean
from .context import NA, Ctx, Out

CALCULATORS: dict = {}
PD_DURATIONS = [60, 120, 300, 600, 1200, 1800, 3600]


def calc(*ids):
    def deco(fn):
        for i in ids:
            CALCULATORS[i] = fn
        return fn
    return deco


# ------------------------------------------------------------------ helpers
def best_window_mean(a: np.ndarray, w: int, lowest=False, min_cov=0.8):
    n = a.size
    if w > n or w <= 0:
        return None, None
    fin = np.isfinite(a)
    cs = np.concatenate([[0.0], np.cumsum(np.where(fin, a, 0.0))])
    cc = np.concatenate([[0], np.cumsum(fin)])
    s = cs[w:] - cs[:-w]
    c = cc[w:] - cc[:-w]
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(c >= w * min_cov, s / np.maximum(c, 1), np.nan)
    if not np.isfinite(m).any():
        return None, None
    i = int(np.nanargmin(m) if lowest else np.nanargmax(m))
    return float(m[i]), i


def best_distance_time(d: np.ndarray, metres: float):
    if d[-1] - d[0] < metres:
        return None, None
    j = np.searchsorted(d, d + metres, side="left")
    ok = j < d.size
    if not ok.any():
        return None, None
    t = np.where(ok, j - np.arange(d.size), np.iinfo(np.int64).max)
    i = int(np.argmin(t))
    return int(t[i]), i


def gas(ctx: Ctx) -> np.ndarray:
    """Grade-adjusted speed via Minetti (2002) energy cost of running, normalised to flat (3.6 J/kg/m)."""
    if "gas" not in ctx.cache:
        sp = ctx.t.ch["speed_smooth"]
        g = np.clip(np.nan_to_num(ctx.t.ch["grade_pct"], nan=0.0) / 100, -0.3, 0.3)
        cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
        ctx.cache["gas"] = np.where(ctx.t.moving, sp * cost / 3.6, np.nan)
    return ctx.cache["gas"]


def ngp_speed(ctx: Ctx):
    g30 = rolling_nanmean(gas(ctx), 30)
    v = g30[ctx.t.moving & np.isfinite(g30)]
    if v.size < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s moving")
    return float(np.mean(v**4) ** 0.25)


def splits(ctx):
    if "splits" not in ctx.cache:
        ctx.cache["splits"] = segmod.km_splits(ctx.t)
    return ctx.cache["splits"]


def split_times(ctx):
    return np.array([int(ctx.t.moving[s.start_s:s.end_s].sum()) for s in splits(ctx)], float)


def steadies(ctx):
    if "steady" not in ctx.cache:
        ctx.cache["steady"] = segmod.steady_segments(ctx.t)
    return ctx.cache["steady"]


def reps(ctx):
    if "intervals" not in ctx.cache:
        ctx.cache["intervals"] = segmod.intervals(ctx.t)
    return ctx.cache["intervals"]


def quarters(ctx):
    idx = np.where(ctx.t.moving)[0]
    if idx.size < 400:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 400 s moving")
    return np.array_split(idx, 4)


def qmean(ctx, f, q):
    a = ctx.t.ch[f][q]
    a = a[np.isfinite(a)]
    if a.size < 30:
        raise NA("INSUFFICIENT_DATA", f"{f} sparse in quarter")
    return float(a.mean())


def hr_after_warmup_halves(ctx):
    idx = np.where(ctx.t.moving)[0]
    idx = idx[idx >= 600]
    if idx.size < 1200:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 20 min moving after a 10 min warm-up")
    return np.array_split(idx, 2)


def est(ctx, *names):
    return bool(set(names) & ctx.th.estimated)


def cv(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if a.size < 3 or a.mean() == 0:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 3 values")
    return float(a.std(ddof=1) / a.mean() * 100)


def theil_sen_per_week(points):
    """points: [(datetime, value)] -> slope per week (or NA)."""
    pts = [(p, v) for p, v in points if v is not None and math.isfinite(v)]
    if len(pts) < 4:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 4 activities")
    t0 = pts[0][0]
    x = np.array([(p - t0).total_seconds() / 86400 for p, _ in pts])
    y = np.array([v for _, v in pts])
    if np.ptp(x) < 7:
        raise NA("INSUFFICIENT_DATA", "history spans < 7 days")
    slope, _, lo, hi = sps.theilslopes(y, x)
    return slope * 7, {"ci95_per_week": [lo * 7, hi * 7], "n": len(pts)}


def series(ctx, metric_id, days=None, include_current=True):
    pts = [(p.start_time, p.metrics.get(metric_id)) for p in ctx.prior(days=days)]
    if include_current:
        pts.append((ctx.t.start_time, ctx.value(metric_id)))
    return [(a, b) for a, b in sorted(pts, key=lambda x: x[0]) if b is not None]


# ------------------------------------------------------------------ running: volume & pace
@calc("running.distance", "swimming.total_distance")
def _distance(ctx):
    if ctx.t.provenance["distance_m"] == "unavailable":
        raise NA("INSUFFICIENT_DATA", "no distance or GPS")
    return Out(round(ctx.t.distance_m, 1), quality=1.0 if ctx.t.provenance["distance_m"] == "measured" else 0.9)


@calc("running.moving_time", "swimming.moving_time")
def _moving(ctx):
    return Out(ctx.t.moving_s)


@calc("running.elapsed_time")
def _elapsed(ctx):
    return Out(ctx.t.n)


@calc("running.avg_pace")
def _avg_pace(ctx):
    d = ctx.t.distance_m
    if d < 100 or ctx.t.moving_s < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 100 m and ≥ 60 s moving")
    return Out(ctx.t.moving_s / (d / 1000))


@calc("swimming.avg_pace_100m")
def _swim_pace(ctx):
    d = ctx.t.distance_m
    if d < 50:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 50 m")
    return Out(ctx.t.moving_s / (d / 100))


@calc("running.avg_speed", "cycling.avg_speed")
def _avg_speed(ctx):
    if ctx.t.moving_s < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s moving")
    return Out(ctx.t.distance_m / ctx.t.moving_s)


@calc("running.max_speed_5s")
def _max_speed(ctx):
    ctx.need("speed_ms")
    v, i = best_window_mean(ctx.t.ch["speed_ms"], 5)
    if v is None:
        raise NA("INSUFFICIENT_DATA", "too short")
    return Out(v, {"at_s": i})


@calc("running.avg_heart_rate", "swimming.avg_heart_rate")
def _avg_hr(ctx):
    ctx.need("heart_rate")
    a = ctx.mv("heart_rate")
    if a.size < 30:
        raise NA("INSUFFICIENT_DATA", "HR while moving < 30 s")
    return Out(float(a.mean()))


@calc("running.max_heart_rate")
def _max_hr(ctx):
    ctx.need("heart_rate")
    v, i = best_window_mean(ctx.t.ch["heart_rate"], 5)
    if v is None:
        raise NA("INSUFFICIENT_DATA", "too short")
    return Out(v, {"at_s": i})


@calc("running.hr_drift")
def _hr_drift(ctx):
    ctx.need("heart_rate")
    h1, h2 = hr_after_warmup_halves(ctx)
    hr = ctx.t.ch["heart_rate"]
    a, b = np.nanmean(hr[h1]), np.nanmean(hr[h2])
    return Out(float(b - a), {"first_half_bpm": float(a), "second_half_bpm": float(b)})


def _ef_halves(ctx):
    ctx.need("heart_rate")
    idx = np.where(ctx.t.moving)[0]
    if idx.size < 1200:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 20 min moving")
    out = []
    for half in np.array_split(idx, 2):
        sp = np.nanmean(ctx.t.ch["speed_smooth"][half])
        hr = np.nanmean(ctx.t.ch["heart_rate"][half])
        out.append(sp * 60 / hr)
    return out


@calc("running.aerobic_decoupling")
def _decoupling(ctx):
    e1, e2 = _ef_halves(ctx)
    return Out(float((e1 - e2) / e1 * 100), {"ef_first": e1, "ef_second": e2})


@calc("running.efficiency_factor")
def _ef(ctx):
    ctx.need("heart_rate")
    hr = ctx.mv("heart_rate")
    if hr.size < 300:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 5 min HR while moving")
    return Out(ngp_speed(ctx) * 60 / float(hr.mean()))


@calc("running.normalized_graded_pace")
def _ngp(ctx):
    return Out(1000 / ngp_speed(ctx), estimated=not ctx.t.has("altitude_m"),
               detail={} if ctx.t.has("altitude_m") else {"note": "no altitude: grade not adjusted"})


@calc("running.grade_adjusted_pace")
def _gap(ctx):
    ctx.need("altitude_m")
    g = gas(ctx)
    v = g[np.isfinite(g)]
    if v.size < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s moving")
    return Out(1000 / float(v.mean()))


@calc("running.pace_cv")
def _pace_cv(ctx):
    ctx.need_moving(300)
    v = rolling_nanmean(ctx.t.ch["speed_ms"], 30)[ctx.t.moving]
    return Out(cv(v))


@calc("running.km_split_cv")
def _km_cv(ctx):
    st = split_times(ctx)
    if st.size < 3:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 3 full km")
    return Out(cv(st), {"splits_s": st.tolist()})


@calc("running.negative_split_ratio")
def _neg(ctx):
    d = ctx.t.ch["distance_m"]
    total = d[-1] - d[0]
    if total < 1000:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 1 km")
    i = int(np.searchsorted(d, d[0] + total / 2))
    t1, t2 = int(ctx.t.moving[:i].sum()), int(ctx.t.moving[i:].sum())
    return Out(t2 / t1 if t1 else None, {"first_half_s": t1, "second_half_s": t2})


@calc("running.fastest_km", "running.slowest_km")
def _km_extreme(ctx):
    raise NA("INVALID_INPUT", "dispatched below")


def _km_ext(ctx, fn):
    st = split_times(ctx)
    if st.size < 1:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 1 full km")
    i = int(fn(st))
    return Out(float(st[i]), {"km": i + 1})


CALCULATORS["running.fastest_km"] = lambda ctx: _km_ext(ctx, np.argmin)
CALCULATORS["running.slowest_km"] = lambda ctx: _km_ext(ctx, np.argmax)


def _best_dist(metres):
    def f(ctx):
        if ctx.t.provenance["distance_m"] == "unavailable":
            raise NA("INSUFFICIENT_DATA", "no distance")
        t, i = best_distance_time(ctx.t.ch["distance_m"], metres)
        if t is None:
            raise NA("NOT_APPLICABLE", f"activity shorter than {metres:.0f} m")
        hr = ctx.t.ch["heart_rate"][i:i + t]
        return Out(float(t), {"start_s": i, "avg_hr": float(np.nanmean(hr)) if np.isfinite(hr).any() else None})
    return f


CALCULATORS["running.best_1km"] = _best_dist(1000)
CALCULATORS["running.best_5km"] = _best_dist(5000)
CALCULATORS["running.best_10km"] = _best_dist(10000)


def _best_pace(w):
    def f(ctx):
        ctx.need("speed_ms")
        v, i = best_window_mean(ctx.t.ch["speed_ms"], w)
        if v is None or v <= 0.3:
            raise NA("NOT_APPLICABLE", f"activity shorter than {w} s")
        return Out(1000 / v, {"start_s": i})
    return f


CALCULATORS["running.best_pace_5min"] = _best_pace(300)
CALCULATORS["running.best_pace_20min"] = _best_pace(1200)


@calc("running.cardiac_cost")
def _cc(ctx):
    ctx.need("heart_rate")
    hr = ctx.t.ch["heart_rate"][ctx.t.moving]
    km = ctx.t.distance_m / 1000
    if km < 0.5 or np.isfinite(hr).mean() < 0.8:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 0.5 km with HR on ≥ 80% of moving time")
    beats = np.nansum(hr) / 60 / np.isfinite(hr).mean()
    return Out(float(beats / km))


ZONES = [(0, .85), (.85, .90), (.90, .95), (.95, 1.0), (1.0, 9)]


def _zone(z):
    lo, hi = ZONES[z - 1]

    def f(ctx):
        ctx.need("heart_rate")
        hr = ctx.mv("heart_rate") / ctx.th.lthr
        return Out(float(((hr >= lo) & (hr < hi)).sum()), estimated=est(ctx, "lthr"),
                   detail={"lthr": ctx.th.lthr})
    return f


for _z in range(1, 6):
    CALCULATORS[f"running.time_hr_z{_z}"] = _zone(_z)


@calc("running.longest_steady_segment")
def _longest_steady(ctx):
    ctx.need("speed_ms")
    st = steadies(ctx)
    if not st:
        return Out(0.0)
    s = max(st, key=lambda x: x.duration_s)
    return Out(float(s.duration_s), {"start_s": s.start_s, "avg_pace_s_km": s.avg_pace_s_km, "avg_hr": s.avg_hr})


# ------------------------------------------------------------------ biomechanics
@calc("biomechanics.avg_cadence", "cycling.avg_cadence")
def _cad(ctx):
    ctx.need("cadence_spm")
    a = ctx.mv("cadence_spm")
    if a.size < 60:
        raise NA("INSUFFICIENT_DATA", "cadence while moving < 60 s")
    return Out(float(a.mean()))


@calc("biomechanics.cadence_cv")
def _cad_cv(ctx):
    ctx.need("cadence_spm")
    return Out(cv(ctx.mv("cadence_spm")))


@calc("biomechanics.cadence_drift")
def _cad_drift(ctx):
    ctx.need("cadence_spm")
    q = quarters(ctx)
    return Out(qmean(ctx, "cadence_spm", q[3]) - qmean(ctx, "cadence_spm", q[0]))


@calc("biomechanics.cadence_final_quarter")
def _cad_q4(ctx):
    ctx.need("cadence_spm")
    return Out(qmean(ctx, "cadence_spm", quarters(ctx)[3]))


@calc("biomechanics.step_rate_variability_late")
def _cad_late_cv(ctx):
    ctx.need("cadence_spm")
    q = quarters(ctx)[3]
    return Out(cv(ctx.t.ch["cadence_spm"][q]))


@calc("biomechanics.avg_stride_length")
def _sl(ctx):
    ctx.need("stride_length_m")
    a = ctx.mv("stride_length_m")
    if a.size < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s")
    return Out(float(a.mean()), estimated=ctx.t.provenance["stride_length_m"] == "derived",
               detail={"provenance": ctx.t.provenance["stride_length_m"]})


@calc("biomechanics.stride_length_cv")
def _sl_cv(ctx):
    ctx.need("stride_length_m")
    return Out(cv(ctx.mv("stride_length_m")))


@calc("biomechanics.stride_length_drift", "risk.late_form_change")
def _sl_drift(ctx):
    ctx.need("stride_length_m")
    q = quarters(ctx)
    a, b = qmean(ctx, "stride_length_m", q[0]), qmean(ctx, "stride_length_m", q[3])
    return Out((b / a - 1) * 100, {"q1_m": a, "q4_m": b})


def _slope(ctx, yf):
    ctx.need(yf, "speed_ms")
    m = ctx.t.moving & np.isfinite(ctx.t.ch[yf]) & np.isfinite(ctx.t.ch["speed_smooth"])
    x, y = ctx.t.ch["speed_smooth"][m], ctx.t.ch[yf][m]
    if x.size < 120 or np.ptp(x) < 0.3:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 2 min and a speed range ≥ 0.3 m/s")
    r = sps.linregress(x, y)
    return Out(float(r.slope), {"r": float(r.rvalue), "n": int(x.size)})


CALCULATORS["biomechanics.cadence_speed_slope"] = lambda ctx: _slope(ctx, "cadence_spm")
CALCULATORS["biomechanics.stride_speed_slope"] = lambda ctx: _slope(ctx, "stride_length_m")


@calc("biomechanics.total_steps")
def _steps(ctx):
    ctx.need("cadence_spm")
    return Out(float(np.nansum(ctx.t.ch["cadence_spm"][ctx.t.moving]) / 60))


def _sensor_mean(field):
    def f(ctx):
        ctx.need(field)
        a = ctx.mv(field)
        if a.size < 60:
            raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s")
        return Out(float(a.mean()))
    return f


CALCULATORS["biomechanics.avg_ground_contact"] = _sensor_mean("ground_contact_ms")
CALCULATORS["biomechanics.avg_vertical_oscillation"] = _sensor_mean("vertical_oscillation_mm")


@calc("biomechanics.cadence_at_easy_pace")
def _cad_easy(ctx):
    ctx.need("cadence_spm")
    m = ctx.t.moving & (ctx.t.ch["speed_smooth"] < 0.85 * ctx.th.threshold_speed)
    a = ctx.t.ch["cadence_spm"][m]
    a = a[np.isfinite(a)]
    if a.size < 120:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 2 min at easy pace")
    return Out(float(a.mean()), estimated=est(ctx, "threshold_pace_s_km"))


@calc("biomechanics.stride_at_threshold_pace")
def _sl_thr(ctx):
    ctx.need("stride_length_m")
    r = rolling_nanmean(ctx.t.ch["speed_ms"], 30) / ctx.th.threshold_speed
    m = ctx.t.moving & (r >= 0.95) & (r <= 1.05)
    a = ctx.t.ch["stride_length_m"][m]
    a = a[np.isfinite(a)]
    if a.size < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s near threshold pace")
    return Out(float(a.mean()), estimated=est(ctx, "threshold_pace_s_km"))


# ------------------------------------------------------------------ environment
@calc("environment.avg_temperature")
def _temp(ctx):
    ctx.need("temperature_c")
    return Out(float(np.nanmean(ctx.t.ch["temperature_c"])))


@calc("environment.max_temperature")
def _tmax(ctx):
    ctx.need("temperature_c")
    return Out(float(np.nanmax(ctx.t.ch["temperature_c"])))


@calc("environment.temperature_range")
def _trange(ctx):
    ctx.need("temperature_c")
    return Out(float(np.nanmax(ctx.t.ch["temperature_c"]) - np.nanmin(ctx.t.ch["temperature_c"])))


def gain_loss(ctx, thr=1.0):
    if "gainloss" not in ctx.cache:
        ctx.need("altitude_m")
        alt = ctx.t.ch["altitude_smooth"]
        alt = alt[np.isfinite(alt)]
        gain = loss = 0.0
        ref = alt[0]
        for v in alt[1:]:
            if v - ref >= thr:
                gain += v - ref
                ref = v
            elif ref - v >= thr:
                loss += ref - v
                ref = v
        ctx.cache["gainloss"] = (gain, loss)
    return ctx.cache["gainloss"]


CALCULATORS["environment.elevation_gain"] = lambda ctx: Out(gain_loss(ctx)[0])
CALCULATORS["environment.elevation_loss"] = lambda ctx: Out(gain_loss(ctx)[1])


def _grade_stat(fn):
    def f(ctx):
        ctx.need("altitude_m")
        g = ctx.mv("grade_pct")
        if g.size < 60:
            raise NA("INSUFFICIENT_DATA", "needs ≥ 60 s of grade")
        return Out(float(fn(g)))
    return f


CALCULATORS["environment.max_grade"] = _grade_stat(np.max)
CALCULATORS["environment.min_grade"] = _grade_stat(np.min)
CALCULATORS["environment.avg_abs_grade"] = _grade_stat(lambda g: np.abs(g).mean())
CALCULATORS["environment.pct_time_climbing"] = _grade_stat(lambda g: (g > 2).mean() * 100)


@calc("environment.climb_rate")
def _climb_rate(ctx):
    km = ctx.t.distance_m / 1000
    if km < 0.5:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 0.5 km")
    return Out(gain_loss(ctx)[0] / km)


@calc("environment.max_altitude")
def _maxalt(ctx):
    ctx.need("altitude_m")
    return Out(float(np.nanmax(ctx.t.ch["altitude_smooth"])))


# ------------------------------------------------------------------ execution
def _need_reps(ctx):
    work, rest = reps(ctx)
    if len(work) < 3:
        raise NA("NOT_APPLICABLE", "no interval structure detected")
    return work, rest


@calc("execution.interval_count")
def _int_count(ctx):
    ctx.need("speed_ms")
    work, _ = reps(ctx)
    return Out(float(len(work)), {"reps": [{"start_s": w.start_s, "duration_s": w.duration_s,
                                            "pace_s_km": w.avg_pace_s_km} for w in work]})


@calc("execution.rep_pace_cv")
def _rep_cv(ctx):
    work, _ = _need_reps(ctx)
    return Out(cv([w.avg_pace_s_km for w in work]))


@calc("execution.rep_duration_cv")
def _rep_dur_cv(ctx):
    work, _ = _need_reps(ctx)
    return Out(cv([w.duration_s for w in work]))


@calc("execution.work_rest_ratio")
def _wr(ctx):
    work, rest = _need_reps(ctx)
    r = sum(x.duration_s for x in rest)
    if not r:
        raise NA("INSUFFICIENT_DATA", "no recoveries")
    return Out(sum(w.duration_s for w in work) / r)


@calc("execution.interval_hr_recovery")
def _int_hrr(ctx):
    ctx.need("heart_rate")
    work, _ = _need_reps(ctx)
    hr = ctx.t.ch["heart_rate"]
    drops = [hr[w.end_s - 1] - hr[w.end_s + 59] for w in work
             if w.end_s + 59 < ctx.t.n and np.isfinite(hr[w.end_s - 1]) and np.isfinite(hr[w.end_s + 59])]
    if not drops:
        raise NA("INSUFFICIENT_DATA", "no 60 s recovery windows")
    return Out(float(np.mean(drops)), {"drops_bpm": [float(x) for x in drops]})


def _pace_of(segs):
    d = sum(s.distance_m for s in segs)
    t = sum(s.duration_s for s in segs)
    if d < 50:
        raise NA("INSUFFICIENT_DATA", "too little distance")
    return t / (d / 1000)


CALCULATORS["execution.avg_work_pace"] = lambda ctx: Out(_pace_of(_need_reps(ctx)[0]))
CALCULATORS["execution.avg_recovery_pace"] = lambda ctx: Out(_pace_of(_need_reps(ctx)[1]))


@calc("execution.rep_fade")
def _rep_fade(ctx):
    work, _ = _need_reps(ctx)
    return Out((work[-1].avg_pace_s_km / work[0].avg_pace_s_km - 1) * 100)


def _pauses(ctx):
    runs, n = [], 0
    for m in ctx.t.moving:
        if not m:
            n += 1
        else:
            if n >= 5:
                runs.append(n)
            n = 0
    if n >= 5:
        runs.append(n)
    return runs


CALCULATORS["execution.pause_count"] = lambda ctx: Out(float(len(_pauses(ctx))))
CALCULATORS["execution.paused_time"] = lambda ctx: Out(float(ctx.t.n - ctx.t.moving_s))
CALCULATORS["execution.moving_ratio"] = lambda ctx: Out(ctx.t.moving_s / ctx.t.n)
CALCULATORS["execution.data_quality"] = lambda ctx: Out(ctx.t.quality["score"], dict(ctx.t.quality["components"]))


@calc("execution.surge_count")
def _surges(ctx):
    ctx.need("speed_ms")
    sp = ctx.t.ch["speed_smooth"]
    base = np.convolve(np.nan_to_num(sp), np.ones(60) / 60, mode="full")[:sp.size]
    run, count = 0, 0
    for v, b in zip(np.nan_to_num(sp), base):
        if b > 0 and v > 1.15 * b and v > 1.5:
            run += 1
            if run == 10:
                count += 1
        else:
            run = 0
    return Out(float(count))


@calc("execution.warmup_duration")
def _warmup(ctx):
    ctx.need("heart_rate")
    hr = ctx.t.ch["heart_rate"]
    if ctx.t.n < 1200:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 20 min")
    ref = np.nanmean(hr[600:1200])
    idx = np.where(np.nan_to_num(hr) >= ref - 5)[0]
    return Out(float(idx[0]) if idx.size else None, {"reference_bpm": float(ref)})


@calc("execution.finish_strength")
def _finish(ctx):
    idx = np.where(ctx.t.moving)[0]
    if idx.size < 600:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 10 min moving")
    tail = idx[-max(1, idx.size // 10):]
    return Out(float(np.nanmean(ctx.t.ch["speed_smooth"][tail]) / (ctx.t.distance_m / ctx.t.moving_s)))


@calc("execution.hr_response_lag")
def _lag(ctx):
    ctx.need("heart_rate", "speed_ms")
    dv = rolling_nanmean(np.diff(ctx.t.ch["speed_smooth"], prepend=np.nan), 15)
    dh = rolling_nanmean(np.diff(ctx.t.ch["heart_rate"], prepend=np.nan), 15)
    best, lag = None, None
    for L in range(0, 61, 3):
        a, b = dv[: dv.size - L], dh[L:]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 300 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
            continue
        c = float(np.corrcoef(a[m], b[m])[0, 1])
        if best is None or c > best:
            best, lag = c, L
    if lag is None or best < 0.1:
        raise NA("INSUFFICIENT_DATA", "speed changes too small to estimate lag")
    return Out(float(lag), {"correlation": best})


@calc("execution.steady_share")
def _steady_share(ctx):
    ctx.need_moving(300)
    return Out(sum(s.duration_s for s in steadies(ctx)) / ctx.t.moving_s * 100)


@calc("execution.pacing_strategy")
def _pacing(ctx):
    ratio = _neg(ctx).value
    pcv = _pace_cv(ctx).value
    if reps(ctx)[0] and len(reps(ctx)[0]) >= 3:
        code, label = 3, "intervals"
    elif pcv > 12:
        code, label = 2, "variable"
    elif ratio < 0.98:
        code, label = -1, "negative split"
    elif ratio > 1.02:
        code, label = 1, "positive split"
    else:
        code, label = 0, "even"
    return Out(float(code), {"label": label, "split_ratio": ratio, "pace_cv": pcv})


# ------------------------------------------------------------------ load
def hrr(ctx, hr):
    return np.clip((hr - ctx.th.rest_hr) / (ctx.th.max_hr - ctx.th.rest_hr), 0, 1.2)


@calc("load.trimp_banister")
def _trimp(ctx):
    ctx.need("heart_rate")
    h = hrr(ctx, ctx.mv("heart_rate"))
    return Out(float(np.sum(h * 0.64 * np.exp(1.92 * h)) / 60), estimated=est(ctx, "max_hr", "rest_hr"))


@calc("load.trimp_edwards")
def _edwards(ctx):
    ctx.need("heart_rate")
    f = ctx.mv("heart_rate") / ctx.th.max_hr
    w = np.where(f >= 0.5, np.clip(np.floor((f - 0.5) * 10) + 1, 1, 5), 0)
    return Out(float(w.sum() / 60), estimated=est(ctx, "max_hr"))


@calc("load.trimp_lucia")
def _lucia(ctx):
    ctx.need("heart_rate")
    h = ctx.mv("heart_rate")
    w = np.where(h < 0.9 * ctx.th.lthr, 1, np.where(h < ctx.th.lthr, 2, 3))
    return Out(float(w.sum() / 60), estimated=est(ctx, "lthr"))


@calc("load.hrtss")
def _hrtss(ctx):
    trimp = _trimp(ctx).value
    r = hrr(ctx, np.array([ctx.th.lthr]))[0]
    per_hour = 60 * r * 0.64 * math.exp(1.92 * r)
    return Out(trimp / per_hour * 100, estimated=est(ctx, "max_hr", "rest_hr", "lthr"))


@calc("load.intensity_factor")
def _if(ctx):
    if ctx.t.sport != "running":
        raise NA("NOT_APPLICABLE", "pace-based IF is for running")
    return Out(ngp_speed(ctx) / ctx.th.threshold_speed, estimated=est(ctx, "threshold_pace_s_km"))


@calc("load.rtss")
def _rtss(ctx):
    i = _if(ctx)
    return Out(ctx.t.moving_s / 3600 * i.value**2 * 100, estimated=i.estimated)


@calc("load.time_above_lthr")
def _above(ctx):
    ctx.need("heart_rate")
    return Out(float((ctx.mv("heart_rate") >= ctx.th.lthr).sum()), estimated=est(ctx, "lthr"))


@calc("load.energy_kcal")
def _kcal(ctx):
    if ctx.t.session.get("total_calories"):
        return Out(float(ctx.t.session["total_calories"]), {"source": "device"})
    if ctx.t.sport != "running" or ctx.t.distance_m < 100:
        raise NA("INSUFFICIENT_DATA", "no device calories and no running estimate")
    return Out(1.036 * ctx.th.weight_kg * ctx.t.distance_m / 1000, {"source": "estimate"}, estimated=True)


@calc("load.session_load")
def _load(ctx):
    for mid in ("load.rtss", "cycling.tss", "load.hrtss"):
        r = ctx.results.get(mid)
        if r is not None and r.value is not None:
            return Out(r.value, {"from": mid}, estimated=r.estimated)
    raise NA("INSUFFICIENT_DATA", "no pace, power or HR load available")


def _hr_zone_share(ctx, zs):
    ctx.need("heart_rate")
    tot = [ctx.value(f"running.time_hr_z{z}") for z in range(1, 6)]
    if any(v is None for v in tot) or not sum(tot):
        f = ctx.mv("heart_rate") / ctx.th.lthr
        tot = [float(((f >= lo) & (f < hi)).sum()) for lo, hi in ZONES]
    return Out(sum(tot[z - 1] for z in zs) / sum(tot) * 100, estimated=est(ctx, "lthr"))


CALCULATORS["load.low_intensity_share"] = lambda ctx: _hr_zone_share(ctx, (1, 2))
CALCULATORS["load.high_intensity_share"] = lambda ctx: _hr_zone_share(ctx, (4, 5))


@calc("load.load_per_km")
def _lpk(ctx):
    v = ctx.value("load.session_load")
    if v is None or ctx.t.distance_m < 500:
        raise NA("INSUFFICIENT_DATA", "needs session load and ≥ 0.5 km")
    return Out(v / (ctx.t.distance_m / 1000))


@calc("load.aerobic_training_effect")
def _te(ctx):
    t = _trimp(ctx)
    return Out(1 + 4 * (1 - math.exp(-t.value / 150)), estimated=True)


def daily_loads(ctx, days=70):
    """Daily session load ending today (today includes this activity). Missing days = 0."""
    today = ctx.t.start_time.date()
    loads = {}
    for p in ctx.prior(sport_only=False, days=days):
        v = p.metrics.get("load.session_load")
        if v is not None:
            loads[p.start_time.date()] = loads.get(p.start_time.date(), 0) + v
    cur = ctx.value("load.session_load")
    if cur is not None:
        loads[today] = loads.get(today, 0) + cur
    return [loads.get(today - dt.timedelta(days=k), 0.0) for k in range(days - 1, -1, -1)]


def _need_history(ctx, n=3, days=42):
    if len(ctx.prior(sport_only=False, days=days)) < n:
        raise NA("INSUFFICIENT_DATA", f"needs ≥ {n} prior activities in {days} days")


def ewma_load(ctx):
    _need_history(ctx)
    L = daily_loads(ctx, 120)
    atl = ctl = 0.0
    atl_hist, ctl_hist = [], []
    for x in L:
        atl += (x - atl) / 7
        ctl += (x - ctl) / 42
        atl_hist.append(atl)
        ctl_hist.append(ctl)
    return atl_hist, ctl_hist, L


CALCULATORS["load.atl"] = lambda ctx: Out(ewma_load(ctx)[0][-1], {"note": "120-day seed window"})
CALCULATORS["load.ctl"] = lambda ctx: Out(ewma_load(ctx)[1][-1], {"note": "120-day seed window"})


@calc("load.tsb")
def _tsb(ctx):
    a, c, _ = ewma_load(ctx)
    return Out(c[-2] - a[-2], {"note": "entering today's session"})


@calc("load.ctl_ramp")
def _ramp(ctx):
    _, c, _ = ewma_load(ctx)
    return Out(c[-1] - c[-8])


@calc("load.acwr", "risk.load_spike_flag")
def _acwr(ctx):
    _need_history(ctx, 4, 28)
    L = daily_loads(ctx, 28)
    chronic = sum(L) / 4
    if chronic <= 0:
        raise NA("INSUFFICIENT_DATA", "no chronic load")
    return Out(sum(L[-7:]) / chronic)


CALCULATORS["risk.load_spike_flag"] = lambda ctx: Out(float(_acwr(ctx).value > 1.5), {"acwr": _acwr(ctx).value})


@calc("load.monotony")
def _monotony(ctx):
    _need_history(ctx, 2, 7)
    L = np.array(daily_loads(ctx, 7))
    if L.std() == 0:
        raise NA("INSUFFICIENT_DATA", "no variation")
    return Out(float(L.mean() / L.std()))


CALCULATORS["load.strain"] = lambda ctx: Out(float(sum(daily_loads(ctx, 7)) * _monotony(ctx).value))
CALCULATORS["load.weekly_load"] = lambda ctx: Out(float(sum(daily_loads(ctx, 7))))


def window_sum(ctx, key, days, offset=0):
    end = ctx.t.start_time - dt.timedelta(days=offset)
    start = end - dt.timedelta(days=days)
    tot = 0.0
    for p in ctx.prior(sport_only=False):
        if start < p.start_time <= end:
            tot += getattr(p, key) if key == "distance_m" else p.metrics.get(key, 0) or 0
    if offset == 0:
        tot += ctx.t.distance_m if key == "distance_m" else (ctx.value(key) or 0)
    return tot


@calc("load.weekly_distance")
def _wdist(ctx):
    _need_history(ctx, 1, 7)
    return Out(window_sum(ctx, "distance_m", 7))


@calc("risk.weekly_distance_jump")
def _wjump(ctx):
    _need_history(ctx, 2, 14)
    a, b = window_sum(ctx, "distance_m", 7), window_sum(ctx, "distance_m", 7, offset=7)
    if b <= 0:
        raise NA("INSUFFICIENT_DATA", "no distance in the previous week")
    return Out((a / b - 1) * 100)


@calc("risk.long_run_share")
def _lrs(ctx):
    _need_history(ctx, 1, 7)
    return Out(ctx.t.distance_m / window_sum(ctx, "distance_m", 7) * 100)


def is_hard(metrics):
    return (metrics.get("load.intensity_factor") or 0) >= 0.9 or (metrics.get("load.time_above_lthr") or 0) >= 600


@calc("risk.consecutive_hard_days")
def _hard_days(ctx):
    _need_history(ctx, 1, 14)
    days = {p.start_time.date() for p in ctx.prior(sport_only=False, days=14) if is_hard(p.metrics)}
    cur = {k: ctx.value(k) for k in ("load.intensity_factor", "load.time_above_lthr")}
    if is_hard(cur):
        days.add(ctx.t.start_time.date())
    n, d = 0, ctx.t.start_time.date()
    while d in days:
        n += 1
        d -= dt.timedelta(days=1)
    return Out(float(n))


@calc("readiness.days_since_last_activity")
def _dsl(ctx):
    pr = ctx.prior(sport_only=False)
    if not pr:
        raise NA("INSUFFICIENT_DATA", "no previous activity")
    last = max(p.start_time for p in pr)
    return Out((ctx.t.start_time - last).total_seconds() / 86400)


@calc("readiness.days_since_hard_session")
def _dsh(ctx):
    hard = [p.start_time for p in ctx.prior(sport_only=False) if is_hard(p.metrics)]
    if not hard:
        raise NA("INSUFFICIENT_DATA", "no previous hard session")
    return Out((ctx.t.start_time - max(hard)).total_seconds() / 86400)


# ------------------------------------------------------------------ progression
def robust_z(x, sample):
    s = np.asarray(sample, float)
    med = np.median(s)
    mad = np.median(np.abs(s - med)) * 1.4826
    if mad == 0:
        mad = np.std(s) or 1e-9
    return float((x - med) / mad), float(med), float(mad)


@calc("progression.ef_vs_baseline")
def _ef_base(ctx):
    cur = ctx.value("running.efficiency_factor")
    prev = [p.metrics["running.efficiency_factor"] for p in ctx.prior(days=90) if p.metrics.get("running.efficiency_factor")]
    if cur is None or len(prev) < 5:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 5 previous activities with efficiency factor")
    z, med, mad = robust_z(cur, prev)
    return Out(z, {"median": med, "mad_scaled": mad, "n": len(prev)})


def _trend(metric_id, days, pct_of_median=False):
    def f(ctx):
        pts = series(ctx, metric_id, days)
        slope, det = theil_sen_per_week(pts)
        if pct_of_median:
            med = float(np.median([v for _, v in pts]))
            slope, det["ci95_per_week"] = slope / med * 100, [x / med * 100 for x in det["ci95_per_week"]]
        return Out(slope, det)
    return f


CALCULATORS["progression.ef_trend_28d"] = _trend("running.efficiency_factor", 28, True)
CALCULATORS["progression.decoupling_trend"] = _trend("running.aerobic_decoupling", 42)
CALCULATORS["progression.cadence_trend"] = _trend("biomechanics.avg_cadence", 42)


def _steady_history(ctx, days=42):
    pts = [(s["avg_hr"], s["avg_pace_s_km"]) for p in ctx.prior(days=days) for s in p.summary.get("steady", [])
           if s.get("avg_hr") and s.get("avg_pace_s_km")]
    pts += [(s.avg_hr, s.avg_pace_s_km) for s in steadies(ctx) if s.avg_hr and s.avg_pace_s_km]
    if len(pts) < 8:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 8 steady segments with HR")
    return np.array(pts)


@calc("progression.pace_at_reference_hr")
def _pace_ref(ctx):
    import statsmodels.api as sm
    a = _steady_history(ctx)
    hr_ref = 0.8 * ctx.th.lthr
    if not (a[:, 0].min() <= hr_ref <= a[:, 0].max()):
        raise NA("INSUFFICIENT_DATA", "reference HR outside observed range")
    fit = sm.RLM(a[:, 1], sm.add_constant(a[:, 0]), M=sm.robust.norms.HuberT()).fit()
    return Out(float(fit.params[0] + fit.params[1] * hr_ref), {"reference_hr": hr_ref, "n": len(a)},
               estimated=est(ctx, "lthr"))


@calc("progression.hr_at_reference_pace")
def _hr_ref(ctx):
    import statsmodels.api as sm
    a = _steady_history(ctx)
    p_ref = ctx.th.threshold_pace_s_km * 1.25
    if not (a[:, 1].min() <= p_ref <= a[:, 1].max()):
        raise NA("INSUFFICIENT_DATA", "reference pace outside observed range")
    fit = sm.RLM(a[:, 0], sm.add_constant(a[:, 1]), M=sm.robust.norms.HuberT()).fit()
    return Out(float(fit.params[0] + fit.params[1] * p_ref), {"reference_pace_s_km": p_ref, "n": len(a)},
               estimated=est(ctx, "threshold_pace_s_km"))


def pd_curve(ctx):
    if "pd" not in ctx.cache:
        out = {}
        for d in PD_DURATIONS:
            v, _ = best_window_mean(ctx.t.ch["speed_ms"], d)
            if v and v > 0.3:
                out[str(d)] = v
        ctx.cache["pd"] = out
    return ctx.cache["pd"]


def prior_best_curve(ctx, days=None):
    best = {}
    for p in ctx.prior(days=days):
        for k, v in (p.summary.get("pd_curve") or {}).items():
            best[k] = max(best.get(k, 0), v)
    return best


@calc("progression.pace_duration_prs")
def _pd_prs(ctx):
    ctx.need("speed_ms")
    prior = prior_best_curve(ctx)
    if not prior:
        raise NA("INSUFFICIENT_DATA", "no previous activities")
    cur = pd_curve(ctx)
    prs = [k for k, v in cur.items() if k in prior and v > prior[k]]
    return Out(float(len(prs)), {"durations_s": prs})


@calc("progression.best_5km_change")
def _b5(ctx):
    cur = ctx.value("running.best_5km")
    prev = [p.metrics["running.best_5km"] for p in ctx.prior() if p.metrics.get("running.best_5km")]
    if cur is None or not prev:
        raise NA("INSUFFICIENT_DATA", "needs a 5 km now and before")
    return Out(cur - min(prev), {"previous_best_s": min(prev)})


@calc("progression.weekly_volume_trend")
def _wvt(ctx):
    _need_history(ctx, 6, 56)
    a = window_sum(ctx, "distance_m", 28)
    b = window_sum(ctx, "distance_m", 28, offset=28)
    if b <= 0:
        raise NA("INSUFFICIENT_DATA", "no volume in prior 4 weeks")
    return Out((a / b - 1) * 100)


@calc("progression.long_run_trend")
def _lrt(ctx):
    now = ctx.t.start_time
    a = [p.distance_m for p in ctx.prior(days=28)] + [ctx.t.distance_m]
    b = [p.distance_m for p in ctx.prior(days=56) if p.start_time < now - dt.timedelta(days=28)]
    if not b:
        raise NA("INSUFFICIENT_DATA", "no runs 28–56 days ago")
    return Out((max(a) / max(b) - 1) * 100)


@calc("progression.split_consistency_trend")
def _sct(ctx):
    now = ctx.t.start_time
    a = [v for _, v in series(ctx, "running.km_split_cv", 28)]
    b = [p.metrics["running.km_split_cv"] for p in ctx.prior(days=56)
         if p.start_time < now - dt.timedelta(days=28) and p.metrics.get("running.km_split_cv") is not None]
    if len(a) < 2 or len(b) < 2:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 2 runs in each 28-day window")
    return Out(float(np.median(a) - np.median(b)))


def _cs_fit(ctx):
    best = prior_best_curve(ctx, days=90)
    for k, v in pd_curve(ctx).items():
        best[k] = max(best.get(k, 0), v)
    pts = [(int(k), v * int(k)) for k, v in best.items() if 180 <= int(k) <= 1200]
    if len(pts) < 3:
        raise NA("INSUFFICIENT_DATA", "needs best efforts at ≥ 3 durations between 3 and 20 min")
    r = sps.linregress([p[0] for p in pts], [p[1] for p in pts])
    return r


CALCULATORS["progression.critical_speed"] = lambda ctx: Out(float(_cs_fit(ctx).slope), {"r2": float(_cs_fit(ctx).rvalue ** 2)})
CALCULATORS["progression.d_prime"] = lambda ctx: Out(float(_cs_fit(ctx).intercept))


@calc("progression.longest_hold_record")
def _lhr(ctx):
    holds = hold_bands(ctx)
    prior = {}
    for p in ctx.prior():
        for k, v in (p.summary.get("holds") or {}).items():
            prior[k] = max(prior.get(k, 0), v["seconds"])
    if not prior:
        raise NA("INSUFFICIENT_DATA", "no previous holds")
    recs = {k: v for k, v in holds.items() if v["seconds"] > prior.get(k, 0) and k in prior}
    if not recs:
        return Out(0.0, {"records": {}})
    k = max(recs, key=lambda x: recs[x]["seconds"])
    return Out(float(recs[k]["seconds"]), {"band_s_km": int(k), "records": recs})


def hold_bands(ctx, width=10):
    """Longest continuous hold per 10 s/km pace band (30 s smoothing, ±3 s/km tolerance, 15 s grace)."""
    if "holds" in ctx.cache:
        return ctx.cache["holds"]
    sp = rolling_nanmean(np.where(ctx.t.moving, ctx.t.ch["speed_ms"], np.nan), 30)
    with np.errstate(divide="ignore", invalid="ignore"):
        pace = np.where(sp > 0.5, 1000 / sp, np.nan)
    hr = ctx.t.ch["heart_rate"]
    out = {}
    fin = pace[np.isfinite(pace)]
    if fin.size < 120:
        ctx.cache["holds"] = out
        return out
    lo, hi = int(np.percentile(fin, 1) // width * width), int(np.percentile(fin, 99) // width * width)
    for b in range(lo, hi + 1, width):
        inside = (pace >= b - 3) & (pace < b + width + 3)
        best, start, outside, bs = 0, None, 0, None
        for i in range(ctx.t.n + 1):
            if i < ctx.t.n and inside[i]:
                start = i if start is None else start
                outside = 0
            elif start is not None:
                outside += 1
                if outside > 15 or i == ctx.t.n:
                    end = i - outside
                    if end - start > best:
                        best, bs = end - start, start
                    start, outside = None, 0
        if best >= 120:
            h = hr[bs:bs + best]
            out[str(b)] = {"seconds": int(best), "start_s": int(bs),
                           "avg_hr": float(np.nanmean(h)) if np.isfinite(h).any() else None}
    ctx.cache["holds"] = out
    return out


@calc("progression.consistency_streak")
def _streak(ctx):
    _need_history(ctx, 3, 28)
    dates = sorted([p.start_time for p in ctx.prior(sport_only=False)] + [ctx.t.start_time])
    weeks = {}
    for d in dates:
        y, w, _ = d.isocalendar()
        weeks[(y, w)] = weeks.get((y, w), 0) + 1
    y, w, _ = ctx.t.start_time.isocalendar()
    monday = dt.date.fromisocalendar(y, w, 1)
    streak = 1 if weeks.get((y, w), 0) >= 3 else 0  # current week counts once it qualifies
    cur = monday - dt.timedelta(days=7)
    while weeks.get(tuple(cur.isocalendar()[:2]), 0) >= 3:
        streak += 1
        cur -= dt.timedelta(days=7)
    return Out(float(streak))


# ------------------------------------------------------------------ cross-workout
def _paired(ctx, xk, yk, days=120, n=8):
    rows = []
    for p in ctx.prior(days=days):
        x = p.metrics.get(xk) if not callable(xk) else xk(p)
        y = p.metrics.get(yk)
        if x is not None and y is not None:
            rows.append((x, y))
    cx = ctx.value(xk) if not callable(xk) else None
    if cx is not None and ctx.value(yk) is not None:
        rows.append((cx, ctx.value(yk)))
    if len(rows) < n:
        raise NA("INSUFFICIENT_DATA", f"needs ≥ {n} activities with both values")
    return np.array(rows, float)


def _spearman(xk, yk):
    def f(ctx):
        a = _paired(ctx, xk, yk)
        rho, p = sps.spearmanr(a[:, 0], a[:, 1])
        return Out(float(rho), {"p_value": float(p), "n": len(a)})
    return f


CALCULATORS["cross.weekly_load_vs_ef"] = _spearman("load.weekly_load", "running.efficiency_factor")
CALCULATORS["cross.cadence_vs_ef"] = _spearman("biomechanics.avg_cadence", "running.efficiency_factor")
CALCULATORS["cross.tsb_vs_efficiency"] = _spearman("load.tsb", "running.efficiency_factor")
CALCULATORS["cross.recovery_days_vs_quality"] = _spearman("readiness.days_since_hard_session", "running.efficiency_factor")


@calc("cross.prior_day_load_vs_decoupling")
def _pdl(ctx):
    by_day = {}
    acts = ctx.prior(sport_only=False, days=120)
    for p in acts:
        by_day[p.start_time.date()] = by_day.get(p.start_time.date(), 0) + (p.metrics.get("load.session_load") or 0)
    rows = [(by_day.get(p.start_time.date() - dt.timedelta(days=1), 0.0), p.metrics["running.aerobic_decoupling"])
            for p in ctx.prior(days=120) if p.metrics.get("running.aerobic_decoupling") is not None]
    if ctx.value("running.aerobic_decoupling") is not None:
        rows.append((by_day.get(ctx.t.start_time.date() - dt.timedelta(days=1), 0.0), ctx.value("running.aerobic_decoupling")))
    if len(rows) < 8:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 8 runs with decoupling")
    a = np.array(rows)
    rho, p = sps.spearmanr(a[:, 0], a[:, 1])
    return Out(float(rho), {"p_value": float(p), "n": len(a)})


def _theil(xk, yk, scale=1.0, min_span=None):
    def f(ctx):
        a = _paired(ctx, xk, yk)
        if min_span and np.ptp(a[:, 0]) < min_span:
            raise NA("INSUFFICIENT_DATA", f"needs a range ≥ {min_span} in {xk}")
        s, _, lo, hi = sps.theilslopes(a[:, 1], a[:, 0])
        return Out(float(s * scale), {"ci95": [lo * scale, hi * scale], "n": len(a)})
    return f


CALCULATORS["cross.temperature_hr_cost"] = _theil("environment.avg_temperature", "running.cardiac_cost", min_span=8)
CALCULATORS["cross.elevation_vs_pace_cost"] = _theil("environment.climb_rate", "running.avg_pace", scale=10, min_span=5)


@calc("cross.time_of_day_efficiency")
def _tod(ctx):
    am, pm = [], []
    for p in ctx.prior(days=180):
        ef = p.metrics.get("running.efficiency_factor")
        if ef is None:
            continue
        h = p.start_time.hour
        (am if h < 10 else pm if h >= 16 else []).append(ef)
    if len(am) < 3 or len(pm) < 3:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 3 morning and ≥ 3 evening runs")
    return Out((np.median(am) / np.median(pm) - 1) * 100, {"n_morning": len(am), "n_evening": len(pm)})


@calc("cross.long_run_vs_next_ef")
def _lr_next(ctx):
    acts = sorted(ctx.prior(days=180), key=lambda p: p.start_time)
    if len(acts) < 10:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 10 runs")
    long_thr = np.percentile([p.distance_m for p in acts], 80)
    efs = [p.metrics.get("running.efficiency_factor") for p in acts]
    med = np.median([e for e in efs if e])
    ch = [efs[i + 1] / med - 1 for i, p in enumerate(acts[:-1]) if p.distance_m >= long_thr and efs[i + 1]]
    if len(ch) < 2:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 2 long runs followed by a run with HR")
    return Out(float(np.mean(ch) * 100), {"n": len(ch)})


# ------------------------------------------------------------------ cycling (power)
def _pw(ctx):
    ctx.need("power_w")
    return np.nan_to_num(ctx.t.ch["power_w"], nan=0.0)


def _np(ctx):
    p30 = np.convolve(_pw(ctx), np.ones(30) / 30, mode="valid")
    if p30.size < 60:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 90 s of power")
    return float(np.mean(p30**4) ** 0.25)


def _ftp(ctx):
    if not ctx.th.ftp_w:
        raise NA("INSUFFICIENT_DATA", "FTP unknown")
    return ctx.th.ftp_w


CALCULATORS["cycling.avg_power"] = lambda ctx: Out(float(_pw(ctx).mean()))
CALCULATORS["cycling.max_power_5s"] = lambda ctx: Out(best_window_mean(_pw(ctx), 5)[0])
CALCULATORS["cycling.normalized_power"] = lambda ctx: Out(_np(ctx))
CALCULATORS["cycling.variability_index"] = lambda ctx: Out(_np(ctx) / float(_pw(ctx).mean()))
CALCULATORS["cycling.intensity_factor"] = lambda ctx: Out(_np(ctx) / _ftp(ctx), estimated=est(ctx, "ftp_w"))
CALCULATORS["cycling.tss"] = lambda ctx: Out(ctx.t.n / 3600 * (_np(ctx) / _ftp(ctx)) ** 2 * 100, estimated=est(ctx, "ftp_w"))
CALCULATORS["cycling.work_kj"] = lambda ctx: Out(float(_pw(ctx).sum() / 1000))


def _best_power(w):
    def f(ctx):
        v, i = best_window_mean(_pw(ctx), w)
        if v is None:
            raise NA("NOT_APPLICABLE", f"shorter than {w} s")
        return Out(v, {"start_s": i})
    return f


CALCULATORS["cycling.best_1min_power"] = _best_power(60)
CALCULATORS["cycling.best_5min_power"] = _best_power(300)
CALCULATORS["cycling.best_20min_power"] = _best_power(1200)
CALCULATORS["cycling.ftp_estimate"] = lambda ctx: Out(0.95 * _best_power(1200)(ctx).value, estimated=True)
CALCULATORS["cycling.watts_per_kg"] = lambda ctx: Out(_best_power(1200)(ctx).value / ctx.th.weight_kg,
                                                     estimated=est(ctx, "weight_kg"))


@calc("cycling.efficiency_factor")
def _cef(ctx):
    ctx.need("heart_rate")
    return Out(_np(ctx) / float(ctx.mv("heart_rate").mean()))


@calc("cycling.power_hr_decoupling")
def _cdec(ctx):
    ctx.need("heart_rate")
    p = _pw(ctx)
    idx = np.where(ctx.t.moving)[0]
    if idx.size < 1200:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 20 min moving")
    e = [p[h].mean() / np.nanmean(ctx.t.ch["heart_rate"][h]) for h in np.array_split(idx, 2)]
    return Out(float((e[0] - e[1]) / e[0] * 100))


@calc("cycling.coasting_share")
def _coast(ctx):
    p = _pw(ctx)
    return Out(float(((p == 0) & ctx.t.moving).sum() / max(ctx.t.moving_s, 1) * 100))


@calc("cycling.vam")
def _vam(ctx):
    ctx.need("altitude_m")
    m = ctx.t.moving & (np.nan_to_num(ctx.t.ch["grade_pct"]) > 3)
    if m.sum() < 120:
        raise NA("INSUFFICIENT_DATA", "needs ≥ 2 min on > 3% grades")
    alt = ctx.t.ch["altitude_smooth"]
    gain = float(np.clip(np.diff(alt), 0, None)[m[1:]].sum())
    return Out(gain / (m.sum() / 3600))


# ------------------------------------------------------------------ post-discovery (second pass)
def _ds(ctx):
    s = ctx.cache.get("discovery_summary")
    if s is None:
        raise NA("INSUFFICIENT_DATA", "discovery engine has not run")
    return s


def _count_class(cls):
    return lambda ctx: Out(float(sum(1 for d in _ds(ctx)["discoveries"] if d["classification"] == cls)))


def _mean_of(key, sub=None):
    def f(ctx):
        ds = _ds(ctx)["discoveries"]
        if not ds:
            raise NA("INSUFFICIENT_DATA", "no discoveries")
        vals = [(d["ranking"][key] if sub else d[key]) for d in ds]
        return Out(float(np.mean(vals)))
    return f


CALCULATORS["discovery.count"] = lambda ctx: Out(float(len(_ds(ctx)["discoveries"])))
CALCULATORS["discovery.top_significance"] = lambda ctx: Out(
    max((d["significance_score"] for d in _ds(ctx)["discoveries"]), default=None)
    if _ds(ctx)["discoveries"] else (_ for _ in ()).throw(NA("INSUFFICIENT_DATA", "no discoveries")))
CALCULATORS["discovery.mean_confidence"] = _mean_of("confidence")
for _cls, _mid in [("PERSONAL_RECORD", "personal_records"), ("EMERGING_PATTERN", "emerging_patterns"),
                   ("CONFIRMED_TREND", "confirmed_trends"), ("ANOMALY", "anomalies"),
                   ("NEW_OBSERVATION", "new_observations")]:
    CALCULATORS[f"discovery.{_mid}"] = _count_class(_cls)
CALCULATORS["discovery.comparable_efforts"] = lambda ctx: Out(float(_ds(ctx)["comparable_matches"]))
CALCULATORS["discovery.match_quality"] = lambda ctx: Out(_ds(ctx)["match_quality"]) if _ds(ctx)["match_quality"] is not None \
    else (_ for _ in ()).throw(NA("INSUFFICIENT_DATA", "no comparable efforts"))
CALCULATORS["discovery.baseline_sample_size"] = lambda ctx: Out(float(len(ctx.prior())))
CALCULATORS["discovery.evidence_items"] = lambda ctx: Out(float(sum(len(d["evidence"]) for d in _ds(ctx)["discoveries"])))
CALCULATORS["discovery.detectors_run"] = lambda ctx: Out(float(_ds(ctx)["detectors_run"]))
CALCULATORS["discovery.detectors_abstained"] = lambda ctx: Out(float(_ds(ctx)["detectors_abstained"]))
CALCULATORS["discovery.data_quality_weight"] = lambda ctx: Out(float(ctx.t.quality["score"]))
CALCULATORS["discovery.goal_relevance"] = _mean_of("goal_relevance", sub=True)
CALCULATORS["discovery.novelty"] = _mean_of("novelty", sub=True)
CALCULATORS["discovery.actionability"] = _mean_of("actionability", sub=True)


@calc("discovery.ai_claims_verified", "discovery.ai_claims_rejected")
def _ai_claims(ctx):
    raise NA("INSUFFICIENT_DATA", "dispatched below")


def _ai(key):
    def f(ctx):
        a = ctx.cache.get("ai_validation")
        if not a or not a.get("total"):
            raise NA("INSUFFICIENT_DATA", "no AI commentary claims")
        return Out(a["verified"] / a["total"] if key == "ratio" else float(a["rejected"]))
    return f


CALCULATORS["discovery.ai_claims_verified"] = _ai("ratio")
CALCULATORS["discovery.ai_claims_rejected"] = _ai("rejected")


def _index_trend(index_id):
    def f(ctx):
        pts = [(p.start_time, (p.summary.get("indexes") or {}).get(index_id)) for p in ctx.prior(days=56)]
        cur = (ctx.cache.get("indexes") or {}).get(index_id)
        pts.append((ctx.t.start_time, cur))
        return Out(*theil_sen_per_week(sorted(pts, key=lambda x: x[0])))
    return f


CALCULATORS["progression.durability_trend"] = _index_trend("durability")
CALCULATORS["progression.aerobic_index_trend"] = _index_trend("aerobic_efficiency")
