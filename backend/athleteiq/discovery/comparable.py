"""Comparable-effort matching. Dissimilar efforts are never compared."""
from __future__ import annotations

import math
from dataclasses import dataclass

VERSION = "comparable-1.0.0"


@dataclass
class Tolerances:
    pace_pct: float = 3.0
    duration_ratio: tuple = (0.7, 1.43)
    grade_abs: float = 1.0
    temp_abs: float = 4.0
    min_quality: float = 0.7
    hr_abs: float | None = None  # when matching by HR instead of pace


def similarity(a: dict, b: dict, tol: Tolerances, by: str = "pace") -> float | None:
    """Returns 0–1 similarity if b is comparable to a under tol, else None.
    a, b: segment dicts with avg_pace_s_km, avg_hr, duration_s, avg_grade, temperature_c, quality."""
    if (b.get("quality") or 0) < tol.min_quality:
        return None
    if by == "pace":
        if not a.get("avg_pace_s_km") or not b.get("avg_pace_s_km"):
            return None
        dp = abs(b["avg_pace_s_km"] / a["avg_pace_s_km"] - 1) * 100
        if dp > tol.pace_pct:
            return None
        s_main = 1 - dp / tol.pace_pct
    else:
        if not a.get("avg_hr") or not b.get("avg_hr"):
            return None
        dh = abs(b["avg_hr"] - a["avg_hr"])
        if dh > (tol.hr_abs or 3):
            return None
        s_main = 1 - dh / (tol.hr_abs or 3)
    r = b["duration_s"] / max(a["duration_s"], 1)
    if not (tol.duration_ratio[0] <= r <= tol.duration_ratio[1]):
        return None
    ga, gb = a.get("avg_grade"), b.get("avg_grade")
    if ga is not None and gb is not None and abs(ga - gb) > tol.grade_abs:
        return None
    ta, tb = a.get("temperature_c"), b.get("temperature_c")
    temp_known = ta is not None and tb is not None
    if temp_known and abs(ta - tb) > tol.temp_abs:
        return None
    s_dur = 1 - abs(math.log(r)) / math.log(tol.duration_ratio[1])
    s_grade = 1 - abs((ga or 0) - (gb or 0)) / tol.grade_abs if (ga is not None and gb is not None) else 0.7
    s_temp = 1 - abs(ta - tb) / tol.temp_abs if temp_known else 0.7
    return round(0.4 * s_main + 0.25 * s_dur + 0.2 * s_grade + 0.15 * s_temp, 3)


def geo_close(a_lat, a_lon, b_lat, b_lon, metres=40.0) -> bool:
    if None in (a_lat, a_lon, b_lat, b_lon):
        return False
    dy = (a_lat - b_lat) * 111_111
    dx = (a_lon - b_lon) * 111_111 * math.cos(math.radians(a_lat))
    return dx * dx + dy * dy <= metres * metres
