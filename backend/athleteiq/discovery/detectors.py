"""The 15 first-release discovery detectors. Each one: find a candidate fact in the current activity,
find comparable history, evaluate statistically, and only then emit a discovery with evidence."""
from __future__ import annotations

import numpy as np

from ..ingestion.normalize import rolling_nanmean
from ..metrics import calculators as C
from .base import Abstain, Candidate, Detector, DetectorContext, Evidence, register
from .comparable import Tolerances, geo_close, similarity
from .stats import confidence, evaluate, magnitude


def fp(s):  # pace formatter
    if s is None:
        return "–"
    m, sec = divmod(int(round(s)), 60)
    return f"{m}:{sec:02d}/km"


def band(b):
    return f"{fp(b)[:-3]}–{fp(b + 10)}"


def fd(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def seg_dict(s):
    return {"avg_pace_s_km": s.avg_pace_s_km, "avg_hr": s.avg_hr, "duration_s": s.duration_s, "avg_grade": s.avg_grade,
            "temperature_c": s.temperature_c, "quality": s.quality, "start_s": s.start_s, "distance_m": s.distance_m,
            "start_lat": s.start_lat, "start_lon": s.start_lon, "end_lat": s.end_lat, "end_lon": s.end_lon,
            "avg_cadence": s.avg_cadence}


def common_limits(ctx, extra=()):
    lim = list(extra)
    if ctx.quality < 0.85:
        lim.append(f"Data quality score {ctx.quality:.2f}: some samples were missing, merged or removed.")
    th = ctx.m.th.estimated
    if th:
        lim.append("Zone/threshold values are estimated (" + ", ".join(sorted(th)) + "); set them in your profile.")
    lim.append("A single session is one observation; repeat under similar conditions before concluding fitness changed.")
    return lim


def series_metric(ctx: DetectorContext, metric_id, filt=None):
    rows = []
    for p in sorted(ctx.m.prior(), key=lambda p: p.start_time):
        v = p.metrics.get(metric_id)
        if v is not None and (filt is None or filt(p)):
            rows.append((p, v))
    return rows


def make(det: Detector, ctx: DetectorContext, ev, title, desc, observed, baseline, evidence, experiment,
         extra_limits=(), match_q=1.0, key="") -> Candidate:
    imp = {"vs_median": ev.improvement_abs, "vs_prior_best": ev.improvement_vs_best, "robust_z": ev.z,
           "bootstrap_ci95": list(ev.ci) if ev.ci else None, "rank": ev.rank, "comparable_n": ev.n,
           "trend_tau": ev.trend_tau, "trend_p": ev.trend_p}
    evidence = list(evidence) + [Evidence("statistic", "Comparison statistics", None, ev.z, "robust z", ev.to_dict())]
    return Candidate(type=det.type, classification=ev.classification, title=title, description=desc,
                     observed_value=observed, baseline_value=baseline, improvement=imp,
                     confidence=confidence(ev, ctx.quality, match_q), magnitude=magnitude(ev),
                     actionability=det.actionability, goal_tags=list(det.goal_tags), evidence=evidence,
                     limitations=common_limits(ctx, extra_limits), recommended_experiment=experiment,
                     dedupe_key=f"{det.type}:{key}")


def metric_ev(mid, value, unit, label=None):
    return Evidence("metric", label or mid, mid, value, unit)


# 1 ------------------------------------------------------------------------------------------
@register
class LongestAtPace(Detector):
    type, actionability, goal_tags = "PACE_DURABILITY_RECORD", 0.8, ("aerobic_base", "race_10k", "half", "marathon", "general")

    def detect(self, ctx):
        holds = C.hold_bands(ctx.m)
        prior = []
        for p in sorted(ctx.m.prior(), key=lambda p: p.start_time):
            prior.append((p, p.summary.get("holds") or {}))
        out = []
        for band_key, h in holds.items():
            if h["seconds"] < 300:
                continue
            hist = [(p, ph[band_key]) for p, ph in prior if band_key in ph]
            ev = evaluate(h["seconds"], [x["seconds"] for _, x in hist], True)
            if ev.classification not in ("PERSONAL_RECORD", "CONFIRMED_TREND") or ev.rank != 1:
                continue
            b = int(band_key)
            prev_p, prev = max(hist, key=lambda x: x[1]["seconds"])
            hr_note, hr_delta = "", None
            close = [x for _, x in hist if x.get("avg_hr") and x["seconds"] >= 0.6 * h["seconds"]]
            if h.get("avg_hr") and close:
                ref = float(np.median([x["avg_hr"] for x in close]))
                hr_delta = h["avg_hr"] - ref
                if hr_delta < -1:
                    hr_note = f" Your average heart rate was {abs(hr_delta):.0f} bpm lower than in your closest comparable holds."
            desc = (f"You held {band(b)} continuously for {fd(h['seconds'])}, starting at {fd(h['start_s'])}. "
                    f"Your previous longest at this pace was {fd(prev['seconds'])} ({prev_p.start_time:%-d %b %Y})." + hr_note)
            exp = {"protocol": f"Within 7–10 days, run {fd(h['seconds'])} continuously at {band(b)} on a similar route "
                               "and time of day.",
                   "success_criterion": (f"Hold the band for ≥ {fd(h['seconds'])} with average HR ≤ {h['avg_hr']:.0f} bpm"
                                         if h.get("avg_hr") else f"Hold the band for ≥ {fd(h['seconds'])}"),
                   "measures": ["progression.longest_hold_record", "running.avg_heart_rate"]}
            out.append(make(self, ctx, ev, f"Longest you've held {band(b)}",
                            desc, {"seconds": h["seconds"], "band_s_km": [b, b + 10], "avg_hr": h.get("avg_hr"),
                                   "start_s": h["start_s"]},
                            {"previous_longest_s": prev["seconds"], "previous_date": prev_p.start_time.isoformat(),
                             "comparable_hold_hr": (h["avg_hr"] - hr_delta) if hr_delta is not None else None},
                            [Evidence("segment", f"Hold {band(b)}", None, h["seconds"], "s", h),
                             Evidence("activity", f"Previous longest ({prev_p.start_time:%-d %b})", prev_p.activity_id,
                                      prev["seconds"], "s", prev)] +
                            ([Evidence("statistic", "HR vs comparable holds", None, hr_delta, "bpm")] if hr_delta is not None else []),
                            exp, ("Pace bands use 30 s smoothing with ±3 s/km tolerance and up to 15 s outside the band.",),
                            key=str(b)))
        out.sort(key=lambda c: -c.observed_value["seconds"])
        return out[:1]


def best_steady_comparison(ctx, by, higher_is_better, value_key):
    """For each steady segment ≥ 5 min, compare value_key against comparable historical steady segments."""
    tol = Tolerances(hr_abs=3.0)
    hist = [(p, s) for p in ctx.m.prior() for s in p.segments if s.get("kind") == "steady"]
    best = None
    for seg in [s for s in ctx.segments if s.kind == "steady" and s.duration_s >= 300]:
        a = seg_dict(seg)
        if a.get(value_key) is None:
            continue
        matches = []
        for p, b in hist:
            sim = similarity(a, b, tol, by=by)
            if sim is not None and b.get(value_key) is not None:
                matches.append((p, b, sim))
        ctx.stats.setdefault("matches", []).extend(m[2] for m in matches)
        if len(matches) < 2:
            continue
        matches.sort(key=lambda m: m[0].start_time)
        ev = evaluate(a[value_key], [b[value_key] for _, b, _ in matches], higher_is_better)
        if ev.classification in (None, "NEW_OBSERVATION"):
            continue
        score = ev.z or 0
        if best is None or score > best[0]:
            best = (score, seg, a, matches, ev)
    return best


# 2 ------------------------------------------------------------------------------------------
@register
class LowestHrAtPace(Detector):
    type, actionability, goal_tags = "AEROBIC_EFFICIENCY_GAIN", 0.7, ("aerobic_base", "general", "marathon", "half")

    def detect(self, ctx):
        if not ctx.m.t.has("heart_rate"):
            raise Abstain("no heart rate")
        r = best_steady_comparison(ctx, "pace", False, "avg_hr")
        if not r:
            raise Abstain("no comparable steady efforts")
        _, seg, a, matches, ev = r
        if ev.classification == "ANOMALY":
            return []  # handled by the HR-pace anomaly detector
        mq = float(np.mean([m[2] for m in matches]))
        desc = (f"For {fd(a['duration_s'])} at {fp(a['avg_pace_s_km'])} (from {fd(a['start_s'])}) your heart rate averaged "
                f"{a['avg_hr']:.0f} bpm. Across {len(matches)} comparable efforts (same pace ±3%, similar duration and gradient"
                f"{', similar temperature' if a.get('temperature_c') is not None else ''}) the median was {ev.median:.0f} bpm.")
        exp = {"protocol": f"Repeat {fd(a['duration_s'])} at {fp(a['avg_pace_s_km'])} on flat ground within 7 days, same time of day.",
               "success_criterion": f"Average HR ≤ {a['avg_hr'] + 2:.0f} bpm (within 2 bpm of today) confirms the shift.",
               "measures": ["running.avg_heart_rate", "running.efficiency_factor"]}
        return [make(self, ctx, ev, f"Lower heart rate at {fp(a['avg_pace_s_km'])}", desc,
                     {"avg_hr": a["avg_hr"], "pace_s_km": a["avg_pace_s_km"], "duration_s": a["duration_s"], "start_s": a["start_s"]},
                     {"median_hr": ev.median, "iqr_hr": list(ev.iqr) if ev.iqr else None, "comparable_n": len(matches)},
                     [Evidence("segment", f"Steady effort at {fp(a['avg_pace_s_km'])}", None, a["avg_hr"], "bpm", a)] +
                     [Evidence("activity", f"Comparable {p.start_time:%-d %b}", p.activity_id, b["avg_hr"], "bpm",
                               {"similarity": s, "pace_s_km": b["avg_pace_s_km"], "duration_s": b["duration_s"]})
                      for p, b, s in matches[-5:]],
                     exp, match_q=mq, key=str(int(a["avg_pace_s_km"] // 10 * 10)))]


# 3 ------------------------------------------------------------------------------------------
@register
class BestPaceAtHr(Detector):
    type, actionability, goal_tags = "PACE_AT_HEART_RATE_GAIN", 0.7, ("aerobic_base", "general", "race_10k", "half")

    def detect(self, ctx):
        if not ctx.m.t.has("heart_rate"):
            raise Abstain("no heart rate")
        r = best_steady_comparison(ctx, "hr", False, "avg_pace_s_km")
        if not r:
            raise Abstain("no comparable steady efforts")
        _, seg, a, matches, ev = r
        if ev.classification == "ANOMALY":
            return []
        mq = float(np.mean([m[2] for m in matches]))
        gain = ev.median - a["avg_pace_s_km"]
        desc = (f"At {a['avg_hr']:.0f} bpm you ran {fp(a['avg_pace_s_km'])} for {fd(a['duration_s'])}. At the same heart rate "
                f"(±3 bpm) your comparable efforts averaged {fp(ev.median)} — {abs(gain):.0f} s/km "
                f"{'faster' if gain > 0 else 'slower'} today.")
        exp = {"protocol": f"Run {fd(a['duration_s'])} capped at {a['avg_hr']:.0f} bpm on a similar route within 7 days.",
               "success_criterion": f"Average pace ≤ {fp(a['avg_pace_s_km'] + 5)} at that cap.",
               "measures": ["progression.pace_at_reference_hr"]}
        return [make(self, ctx, ev, f"Faster at {a['avg_hr']:.0f} bpm", desc,
                     {"pace_s_km": a["avg_pace_s_km"], "avg_hr": a["avg_hr"], "duration_s": a["duration_s"], "start_s": a["start_s"]},
                     {"median_pace_s_km": ev.median, "comparable_n": len(matches)},
                     [Evidence("segment", f"Steady effort at {a['avg_hr']:.0f} bpm", None, a["avg_pace_s_km"], "s/km", a)] +
                     [Evidence("activity", f"Comparable {p.start_time:%-d %b}", p.activity_id, b["avg_pace_s_km"], "s/km",
                               {"similarity": s, "avg_hr": b["avg_hr"]}) for p, b, s in matches[-5:]],
                     exp, match_q=mq, key=str(int(a["avg_hr"] // 5 * 5)))]


def comparable_runs(ctx, ratio=(0.7, 1.43), field="moving_s", min_value=None):
    cur = ctx.m.t.moving_s if field == "moving_s" else ctx.m.t.distance_m
    if min_value and cur < min_value:
        return None
    return lambda p: ratio[0] <= (getattr(p, field) / max(cur, 1)) <= ratio[1]


def series_detector(det, ctx, metric_id, higher, filt, title_fn, desc_fn, exp, unit, limits=(), allowed=None):
    cur = ctx.metrics.get(metric_id)
    if cur is None:
        raise Abstain(f"{metric_id} unavailable")
    if filt is None:
        raise Abstain("activity outside detector scope")
    hist = series_metric(ctx, metric_id, filt)
    ev = evaluate(cur, [v for _, v in hist], higher)
    allowed = allowed or ("PERSONAL_RECORD", "EMERGING_PATTERN", "CONFIRMED_TREND")
    if ev.classification not in allowed:
        return []
    best_p = (max if higher else min)(hist, key=lambda x: x[1])[0] if hist else None
    return [make(det, ctx, ev, title_fn(cur, ev), desc_fn(cur, ev, hist, best_p),
                 {"value": cur, "unit": unit}, {"median": ev.median, "prior_best": ev.prior_best, "comparable_n": ev.n},
                 [metric_ev(metric_id, cur, unit)] +
                 [Evidence("activity", f"{p.start_time:%-d %b}", p.activity_id, v, unit) for p, v in hist[-5:]],
                 exp, limits, key=metric_id)]


# 4 ------------------------------------------------------------------------------------------
@register
class LowestDrift(Detector):
    type, actionability, goal_tags = "DURABILITY_GAIN", 0.6, ("aerobic_base", "half", "marathon", "general")

    def detect(self, ctx):
        filt = comparable_runs(ctx, min_value=2700)
        if ctx.metrics.get("execution.interval_count", 0) >= 3:
            raise Abstain("interval session")
        return series_detector(
            self, ctx, "running.aerobic_decoupling", False, filt,
            lambda c, ev: f"Most durable long effort: {c:+.1f}% decoupling",
            lambda c, ev, h, bp: (f"Pace-to-heart-rate decoupling was {c:+.1f}% over {fd(ctx.m.t.moving_s)}. Across {ev.n} "
                                  f"runs of similar duration your median was {ev.median:+.1f}%."),
            {"protocol": f"Repeat a {fd(ctx.m.t.moving_s)} steady run at the same average pace within 10 days.",
             "success_criterion": f"Decoupling ≤ {ctx.metrics['running.aerobic_decoupling'] + 1:.1f}%",
             "measures": ["running.aerobic_decoupling"]}, "%",
            ("Decoupling is sensitive to heat, hills and pacing changes between halves.",))


# 5 ------------------------------------------------------------------------------------------
@register
class NegativeSplit(Detector):
    type, actionability, goal_tags = "PACING_SKILL", 0.75, ("race_5k", "race_10k", "half", "marathon", "general")

    def detect(self, ctx):
        r = ctx.metrics.get("running.negative_split_ratio")
        if r is None or r >= 0.99:
            raise Abstain("not a negative split")
        if ctx.metrics.get("execution.interval_count", 0) >= 3:
            raise Abstain("interval session")
        filt = comparable_runs(ctx, field="distance_m", ratio=(0.75, 1.33), min_value=3000)
        return series_detector(
            self, ctx, "running.negative_split_ratio", False, filt,
            lambda c, ev: f"Best negative split at this distance ({(1 - c) * 100:.1f}% faster)",
            lambda c, ev, h, bp: (f"Your second half took {(1 - c) * 100:.1f}% less time than the first over "
                                  f"{ctx.m.t.distance_m / 1000:.1f} km — the strongest finish among {ev.n} comparable runs."),
            {"protocol": "On your next run of similar distance, start 5 s/km slower than goal pace for the first half.",
             "success_criterion": "Split ratio < 0.99 again with equal or lower average HR.",
             "measures": ["running.negative_split_ratio"]}, "ratio")


# 6 ------------------------------------------------------------------------------------------
@register
class SplitConsistency(Detector):
    type, actionability, goal_tags = "PACING_CONSISTENCY", 0.6, ("race_5k", "race_10k", "half", "marathon")

    def detect(self, ctx):
        if ctx.metrics.get("execution.interval_count", 0) >= 3:
            raise Abstain("interval session")
        filt = comparable_runs(ctx, field="distance_m", ratio=(0.7, 1.43), min_value=5000)
        return series_detector(
            self, ctx, "running.km_split_cv", False, filt,
            lambda c, ev: f"Your most even kilometres ({c:.1f}% variation)",
            lambda c, ev, h, bp: (f"Kilometre splits varied by {c:.1f}% (coefficient of variation) versus a median of "
                                  f"{ev.median:.1f}% across {ev.n} runs of similar distance."),
            {"protocol": "Repeat the same distance targeting the same average pace without looking at instant pace.",
             "success_criterion": f"Split CV ≤ {ctx.metrics.get('running.km_split_cv', 0) + 0.5:.1f}%",
             "measures": ["running.km_split_cv"]}, "%", ("Hilly routes inflate split variation.",))


# 7 ------------------------------------------------------------------------------------------
@register
class CadenceStability(Detector):
    type, actionability, goal_tags = "FORM_STABILITY", 0.5, ("general", "half", "marathon")

    def detect(self, ctx):
        if ctx.metrics.get("execution.interval_count", 0) >= 3:
            raise Abstain("interval session")
        return series_detector(
            self, ctx, "biomechanics.cadence_cv", False, comparable_runs(ctx, min_value=1200),
            lambda c, ev: f"Steadiest cadence ({c:.1f}% variation)",
            lambda c, ev, h, bp: (f"Cadence varied by only {c:.1f}% (median {ev.median:.1f}% across {ev.n} comparable runs) at an "
                                  f"average of {ctx.metrics.get('biomechanics.avg_cadence', 0):.0f} spm."),
            {"protocol": "Hold the same cadence ±3 spm through the final quarter of your next similar run.",
             "success_criterion": "Cadence drift between first and last quarter within ±2 spm.",
             "measures": ["biomechanics.cadence_cv", "biomechanics.cadence_drift"]}, "%")


def is_interval(p):
    return (p.metrics.get("execution.interval_count") or 0) >= 3


# 8 ------------------------------------------------------------------------------------------
@register
class HrRecovery(Detector):
    type, actionability, goal_tags = "HEART_RATE_RECOVERY", 0.5, ("race_5k", "speed", "general")

    def detect(self, ctx):
        if (ctx.metrics.get("execution.interval_count") or 0) < 3:
            raise Abstain("no intervals")
        return series_detector(
            self, ctx, "execution.interval_hr_recovery", True, is_interval,
            lambda c, ev: f"Fastest heart-rate recovery between reps ({c:.0f} bpm/min)",
            lambda c, ev, h, bp: (f"Heart rate dropped by {c:.0f} bpm on average in the first 60 s of each recovery, versus a "
                                  f"median of {ev.median:.0f} bpm across {ev.n} previous interval sessions."),
            {"protocol": "Repeat the session structure (same reps and recoveries) within 14 days.",
             "success_criterion": f"Mean 60 s HR drop ≥ {ctx.metrics['execution.interval_hr_recovery'] - 2:.0f} bpm.",
             "measures": ["execution.interval_hr_recovery"]}, "bpm",
            ("Recovery HR depends on recovery type (jog vs stand) and rep intensity.",))


# 9 ------------------------------------------------------------------------------------------
@register
class IntervalConsistency(Detector):
    type, actionability, goal_tags = "INTERVAL_EXECUTION", 0.7, ("race_5k", "race_10k", "speed")

    def detect(self, ctx):
        n = ctx.metrics.get("execution.interval_count") or 0
        if n < 3:
            raise Abstain("no intervals")
        return series_detector(
            self, ctx, "execution.rep_pace_cv", False,
            lambda p: is_interval(p) and abs((p.metrics.get("execution.interval_count") or 0) - n) <= 2,
            lambda c, ev: f"Most consistent reps ({c:.1f}% pace variation)",
            lambda c, ev, h, bp: (f"Across {n:.0f} reps your pace varied by {c:.1f}%; similar sessions (±2 reps) had a median of "
                                  f"{ev.median:.1f}%."),
            {"protocol": "Repeat the session aiming for the same average rep pace.",
             "success_criterion": f"Rep pace CV ≤ {ctx.metrics['execution.rep_pace_cv'] + 0.5:.1f}% and rep fade ≤ 2%.",
             "measures": ["execution.rep_pace_cv", "execution.rep_fade"]}, "%")


# 10 -----------------------------------------------------------------------------------------
def aerobic_longest(ctx_m):
    """Longest continuous moving stretch with HR below the top of zone 2 (0.90 × LTHR), 15 s grace."""
    hr = ctx_m.t.ch["heart_rate"]
    cap = 0.90 * ctx_m.th.lthr
    ok = ctx_m.t.moving & np.isfinite(hr) & (hr < cap)
    best = start = 0
    run_start, grace = None, 0
    for i in range(ctx_m.t.n + 1):
        if i < ctx_m.t.n and ok[i]:
            run_start = i if run_start is None else run_start
            grace = 0
        elif run_start is not None:
            grace += 1
            if grace > 15 or i == ctx_m.t.n:
                end = i - grace
                if end - run_start > best:
                    best, start = end - run_start, run_start
                run_start, grace = None, 0
    return int(best), int(start), cap


@register
class LongestAerobic(Detector):
    type, actionability, goal_tags = "AEROBIC_ENDURANCE_RECORD", 0.6, ("aerobic_base", "half", "marathon")

    def detect(self, ctx):
        if not ctx.m.t.has("heart_rate"):
            raise Abstain("no heart rate")
        secs, start, cap = aerobic_longest(ctx.m)
        if secs < 1200:
            raise Abstain("no aerobic stretch ≥ 20 min")
        hist = [(p, p.summary["aerobic_longest"]) for p in sorted(ctx.m.prior(), key=lambda p: p.start_time)
                if p.summary.get("aerobic_longest")]
        ev = evaluate(secs, [v for _, v in hist], True)
        if ev.classification not in ("PERSONAL_RECORD", "CONFIRMED_TREND"):
            return []
        d0, d1 = ctx.m.t.ch["distance_m"][start], ctx.m.t.ch["distance_m"][start + secs - 1]
        return [make(self, ctx, ev, f"Longest continuous aerobic effort: {fd(secs)}",
                     f"You ran {fd(secs)} ({(d1 - d0) / 1000:.1f} km) without heart rate rising above {cap:.0f} bpm "
                     f"(top of zone 2). Your previous longest was {fd(ev.prior_best) if ev.prior_best else '–'}.",
                     {"seconds": secs, "start_s": start, "hr_cap": cap, "distance_m": d1 - d0},
                     {"prior_best_s": ev.prior_best, "comparable_n": ev.n},
                     [Evidence("segment", "Aerobic stretch", None, secs, "s", {"start_s": start, "hr_cap": cap})] +
                     [Evidence("activity", f"{p.start_time:%-d %b}", p.activity_id, v, "s") for p, v in hist[-5:]],
                     {"protocol": f"Next long run, extend the capped-HR stretch by 10% ({fd(secs * 1.1)}).",
                      "success_criterion": f"HR stays < {cap:.0f} bpm for ≥ {fd(secs * 1.1)}.",
                      "measures": ["running.time_hr_z1", "running.time_hr_z2"]},
                     ("Zone-2 ceiling depends on LTHR accuracy.",), key="aerobic")]


# 11 -----------------------------------------------------------------------------------------
@register
class SegmentImprovement(Detector):
    type, actionability, goal_tags = "ROUTE_SEGMENT_IMPROVEMENT", 0.65, ("general", "race_5k", "race_10k")

    def detect(self, ctx):
        splits = [s for s in ctx.segments if s.kind == "split_km" and s.start_lat is not None]
        if not splits:
            raise Abstain("no GPS splits")
        hist = [(p, s) for p in ctx.m.prior() for s in p.segments if s.get("kind") == "split_km"]
        best = None
        for s in splits:
            matches = [(p, b) for p, b in hist if geo_close(s.start_lat, s.start_lon, b.get("start_lat"), b.get("start_lon"))
                       and geo_close(s.end_lat, s.end_lon, b.get("end_lat"), b.get("end_lon"))
                       and b.get("duration_s")]
            if len(matches) < 2:
                continue
            ctx.stats.setdefault("matches", []).extend([0.9] * len(matches))
            matches.sort(key=lambda m: m[0].start_time)
            ev = evaluate(s.duration_s, [b["duration_s"] for _, b in matches], False)
            if ev.classification not in ("PERSONAL_RECORD", "EMERGING_PATTERN", "CONFIRMED_TREND"):
                continue
            hr_ok = (s.avg_hr is None or not any(b.get("avg_hr") for _, b in matches) or
                     s.avg_hr <= np.median([b["avg_hr"] for _, b in matches if b.get("avg_hr")]) + 2)
            if hr_ok and (best is None or (ev.improvement_abs or 0) > (best[1].improvement_abs or 0)):
                best = (s, ev, matches)
        if not best:
            return []
        s, ev, matches = best
        hr_txt = f" at {s.avg_hr:.0f} bpm" if s.avg_hr else ""
        return [make(self, ctx, ev, f"Fastest time on a repeated stretch ({s.label})",
                     f"The kilometre starting at {fd(s.start_s)} follows the same start and end points (±40 m) as {ev.n} previous "
                     f"runs. Today: {fd(s.duration_s)}{hr_txt}; median of those: {fd(ev.median)}.",
                     {"seconds": s.duration_s, "avg_hr": s.avg_hr, "label": s.label},
                     {"median_s": ev.median, "prior_best_s": ev.prior_best, "comparable_n": ev.n},
                     [Evidence("segment", s.label, None, s.duration_s, "s", seg_dict(s))] +
                     [Evidence("activity", f"Same stretch {p.start_time:%-d %b}", p.activity_id, b["duration_s"], "s",
                               {"avg_hr": b.get("avg_hr")}) for p, b in matches[-5:]],
                     {"protocol": "Run this stretch again at the same effort within 2 weeks.",
                      "success_criterion": f"Time ≤ {fd(s.duration_s + 3)} with HR no higher than today.",
                      "measures": ["running.fastest_km"]},
                     ("Wind and traffic are not accounted for.",), key=f"{s.start_lat:.3f},{s.start_lon:.3f}")]


# 12 -----------------------------------------------------------------------------------------
@register
class PaceDurationRecord(Detector):
    type, actionability, goal_tags = "PACE_DURATION_RECORD", 0.6, ("race_5k", "race_10k", "speed", "general")

    def detect(self, ctx):
        cur = C.pd_curve(ctx.m)
        best = None
        for d, v in cur.items():
            hist = [(p, p.summary["pd_curve"][d]) for p in sorted(ctx.m.prior(), key=lambda p: p.start_time)
                    if (p.summary.get("pd_curve") or {}).get(d)]
            if len(hist) < 2:
                continue
            ev = evaluate(v, [x for _, x in hist], True)
            if ev.classification != "PERSONAL_RECORD":
                continue
            rel = (v / ev.prior_best - 1) if ev.prior_best else 0
            if best is None or rel > best[0]:
                best = (rel, d, v, ev, hist)
        if not best:
            return []
        rel, d, v, ev, hist = best
        d = int(d)
        prior_best = C.prior_best_curve(ctx.m)
        prs = [k for k, x in cur.items() if k in prior_best and x > prior_best[k]]
        return [make(self, ctx, ev, f"Best {fd(d)} pace on record: {fp(1000 / v)}",
                     f"Your fastest {fd(d)} today averaged {fp(1000 / v)}, {rel * 100:.1f}% faster than your previous best "
                     f"({fp(1000 / ev.prior_best)}) across {ev.n} activities." +
                     (f" Records at {len(prs)} durations in total." if len(prs) > 1 else ""),
                     {"duration_s": d, "pace_s_km": 1000 / v, "records_at_durations_s": [int(x) for x in prs]},
                     {"prior_best_pace_s_km": 1000 / ev.prior_best, "comparable_n": ev.n},
                     [metric_ev("progression.pace_duration_prs", float(len(prs)), "count")] +
                     [Evidence("activity", f"{p.start_time:%-d %b}", p.activity_id, 1000 / x, "s/km") for p, x in hist[-5:]],
                     {"protocol": f"Within 3 weeks, schedule a dedicated {fd(d)} effort after an easy day.",
                      "success_criterion": f"Average pace ≤ {fp(1000 / v)}.", "measures": ["running.best_pace_5min",
                                                                                         "running.best_pace_20min"]},
                     ("Best-effort windows inside training runs are usually sub-maximal.",), key=str(d))]


# 13 -----------------------------------------------------------------------------------------
@register
class ElevationAdjusted(Detector):
    type, actionability, goal_tags = "HILL_EFFICIENCY", 0.55, ("trail", "general", "marathon")

    def detect(self, ctx):
        cr = ctx.metrics.get("environment.climb_rate")
        if cr is None or cr < 10:
            raise Abstain("not a hilly run")
        return series_detector(
            self, ctx, "running.efficiency_factor", True,
            lambda p: (p.metrics.get("environment.climb_rate") or 0) >= 10,
            lambda c, ev: "Most efficient hilly run (grade-adjusted)",
            lambda c, ev, h, bp: (f"With {cr:.0f} m of climbing per km, your grade-adjusted efficiency was {c:.3f} m/min per beat, "
                                  f"versus a median of {ev.median:.3f} on {ev.n} other hilly runs."),
            {"protocol": "Repeat a similarly hilly route at the same perceived effort.",
             "success_criterion": f"Efficiency factor ≥ {ctx.metrics['running.efficiency_factor'] - 0.02:.3f}.",
             "measures": ["running.efficiency_factor", "running.normalized_graded_pace"]}, "m/min/bpm",
            ("Grade adjustment uses Minetti's energy-cost model, validated on treadmill gradients up to ±45%.",))


# 14 -----------------------------------------------------------------------------------------
@register
class HrPaceAnomaly(Detector):
    type, actionability, goal_tags = "HEART_RATE_PACE_DEVIATION", 0.5, ("general",)

    def detect(self, ctx):
        import statsmodels.api as sm
        if not ctx.m.t.has("heart_rate"):
            raise Abstain("no heart rate")
        hist = [s for p in ctx.m.prior(days=90) for s in p.segments
                if s.get("kind") == "steady" and s.get("avg_hr") and s.get("avg_pace_s_km") and (s.get("quality") or 0) >= 0.7]
        if len(hist) < 10:
            raise Abstain("needs ≥ 10 historical steady segments")
        x = np.array([1000 / s["avg_pace_s_km"] for s in hist])
        y = np.array([s["avg_hr"] for s in hist])
        fit = sm.RLM(y, sm.add_constant(x), M=sm.robust.norms.HuberT()).fit()
        resid = y - fit.predict(sm.add_constant(x))
        scale = float(np.median(np.abs(resid - np.median(resid))) * 1.4826) or 1.0
        cur = [s for s in ctx.segments if s.kind == "steady" and s.avg_hr and s.avg_pace_s_km and s.duration_s >= 300]
        if not cur:
            raise Abstain("no steady segment today")
        dev = []
        for s in cur:
            v = 1000 / s.avg_pace_s_km
            if not (x.min() <= v <= x.max()):
                continue
            pred = float(fit.params[0] + fit.params[1] * v)
            dev.append((s.avg_hr - pred, s, pred))
        if not dev:
            raise Abstain("today's paces outside historical range")
        d, s, pred = max(dev, key=lambda t: abs(t[0]))
        z = d / scale
        if abs(z) < 2.5:
            return []
        from .stats import Evaluation
        ev = Evaluation("ANOMALY", len(hist), pred, None, float(-z), None, None, None, None, None, float(-d), None)
        direction = "higher" if d > 0 else "lower"
        cand = make(self, ctx, ev, f"Heart rate {abs(d):.0f} bpm {direction} than usual for {fp(s.avg_pace_s_km)}",
                    f"For {fd(s.duration_s)} at {fp(s.avg_pace_s_km)}, HR averaged {s.avg_hr:.0f} bpm. Your usual heart rate for that "
                    f"pace (robust fit across {len(hist)} steady efforts in 90 days) is {pred:.0f} bpm. Heat, fatigue, illness, "
                    "dehydration, caffeine or a sensor issue can each cause this; the data alone cannot tell which.",
                    {"avg_hr": s.avg_hr, "pace_s_km": s.avg_pace_s_km, "duration_s": s.duration_s, "start_s": s.start_s},
                    {"expected_hr": pred, "residual_scale_bpm": scale, "segments_n": len(hist)},
                    [Evidence("segment", "Steady effort", None, s.avg_hr, "bpm", seg_dict(s)),
                     Evidence("statistic", "Residual vs personal HR–pace fit", None, d, "bpm",
                              {"robust_z": z, "intercept": float(fit.params[0]), "slope": float(fit.params[1])})],
                    {"protocol": "Note sleep, heat and how you felt; repeat an easy run at the same pace within 3 days.",
                     "success_criterion": f"HR within ±{2 * scale:.0f} bpm of {pred:.0f} on the repeat.",
                     "measures": ["running.avg_heart_rate", "running.cardiac_cost"]},
                    ("This is a deviation from your own pattern, not a medical finding. Optical HR is error-prone.",),
                    key="anomaly")
        cand.confidence = round(min(1.0, abs(z) / 5) * ctx.quality, 3)
        return [cand]


# 15 -----------------------------------------------------------------------------------------
@register
class EnvironmentComparable(Detector):
    type, actionability, goal_tags = "CONDITIONS_ADJUSTED_GAIN", 0.6, ("general", "aerobic_base")

    def detect(self, ctx):
        t = ctx.metrics.get("environment.avg_temperature")
        if t is None:
            raise Abstain("no temperature")
        return series_detector(
            self, ctx, "running.efficiency_factor", True,
            lambda p: (p.metrics.get("environment.avg_temperature") is not None
                       and abs(p.metrics["environment.avg_temperature"] - t) <= 3
                       and 0.6 <= p.moving_s / max(ctx.m.t.moving_s, 1) <= 1.6),
            lambda c, ev: f"Best efficiency in {t:.0f} °C conditions",
            lambda c, ev, h, bp: (f"In runs within ±3 °C of today's {t:.0f} °C and of similar duration, your efficiency factor "
                                  f"median was {ev.median:.3f}; today it was {c:.3f}."),
            {"protocol": "Repeat in similar temperature at the same time of day.",
             "success_criterion": f"Efficiency factor ≥ {ctx.metrics.get('running.efficiency_factor', 0) - 0.02:.3f}.",
             "measures": ["running.efficiency_factor"]}, "m/min/bpm",
            ("Device temperature reflects body heat as well as air temperature.",))
