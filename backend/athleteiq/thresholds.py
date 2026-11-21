"""Resolve athlete thresholds: user-set values win; otherwise estimate and flag as estimated."""
from __future__ import annotations

import numpy as np

from .metrics.calculators import best_window_mean
from .metrics.context import PriorActivity, Thresholds


def resolve(athlete, telemetry, history: list[PriorActivity]) -> Thresholds:
    est = set()
    hr_obs = [p.metrics.get("running.max_heart_rate") for p in history if p.metrics.get("running.max_heart_rate")]
    cur_hr, _ = best_window_mean(telemetry.ch["heart_rate"], 5) if telemetry.has("heart_rate") else (None, None)
    if cur_hr:
        hr_obs.append(cur_hr)

    max_hr = athlete.max_hr
    if not max_hr:
        age_based = (220 - (telemetry.start_time.year - athlete.birth_year)) if athlete.birth_year else None
        candidates = [x for x in (max(hr_obs) if hr_obs else None, age_based) if x]
        max_hr = max(candidates) if candidates else 190.0
        est.add("max_hr")
    rest = athlete.rest_hr or 60.0
    if not athlete.rest_hr:
        est.add("rest_hr")
    lthr = athlete.lthr or round(0.89 * max_hr)
    if not athlete.lthr:
        est.add("lthr")

    tp = athlete.threshold_pace_s_km
    if not tp:
        bests = [1000 / p.summary["pd_curve"]["1200"] for p in history if (p.summary.get("pd_curve") or {}).get("1200")]
        v, _ = best_window_mean(telemetry.ch["speed_ms"], 1200)
        if v and v > 0.5:
            bests.append(1000 / v)
        tp = (min(bests) / 0.93) if bests else 330.0  # threshold ≈ 93% of best 20-min speed
        est.add("threshold_pace_s_km")

    ftp = athlete.ftp_w
    if not ftp and telemetry.has("power_w"):
        v, _ = best_window_mean(np.nan_to_num(telemetry.ch["power_w"]), 1200)
        if v:
            ftp = 0.95 * v
            est.add("ftp_w")
    weight = athlete.weight_kg or 70.0
    if not athlete.weight_kg:
        est.add("weight_kg")
    return Thresholds(max_hr=float(max_hr), rest_hr=float(rest), lthr=float(lthr), threshold_pace_s_km=float(tp),
                      ftp_w=ftp, weight_kg=float(weight), estimated=est)
