"""Segment extraction shared by metrics and discovery: km splits, steady efforts, intervals."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ingestion.normalize import Telemetry, rolling_nanmean

VERSION = "segments-1.0.0"


@dataclass
class Segment:
    kind: str  # split_km | steady | interval | recovery
    start_s: int
    end_s: int  # exclusive
    distance_m: float
    avg_pace_s_km: float | None
    avg_hr: float | None
    avg_cadence: float | None
    avg_grade: float | None
    elev_gain_m: float | None
    temperature_c: float | None
    pace_cv: float | None
    quality: float
    start_lat: float | None = None
    start_lon: float | None = None
    end_lat: float | None = None
    end_lon: float | None = None
    label: str = ""

    @property
    def duration_s(self) -> int:
        return self.end_s - self.start_s


def _nanmean(a):
    a = a[np.isfinite(a)]
    return float(a.mean()) if a.size else None


def make_segment(t: Telemetry, kind: str, s: int, e: int, label: str = "") -> Segment:
    e = max(e, s + 1)
    d = t.ch["distance_m"]
    dist = float(d[e - 1] - d[s]) if e - 1 > s else 0.0
    mv = t.moving[s:e]
    moving_s = int(mv.sum())
    pace = (moving_s / (dist / 1000)) if dist > 10 and moving_s else None
    sp = t.ch["speed_smooth"][s:e][mv]
    sp = sp[np.isfinite(sp)]
    cv = float(sp.std() / sp.mean() * 100) if sp.size > 10 and sp.mean() > 0 else None
    alt = t.ch["altitude_smooth"][s:e]
    alt = alt[np.isfinite(alt)]
    gain = float(np.clip(np.diff(alt), 0, None).sum()) if alt.size > 1 else None
    hr = t.ch["heart_rate"][s:e]
    hr_cov = np.isfinite(hr).mean() if e > s else 0
    lat, lon = t.ch["lat"], t.ch["lon"]

    def first_fin(a, rng):
        for i in rng:
            if np.isfinite(a[i]):
                return float(a[i])
        return None
    q = float(min(1.0, t.quality.get("score", 1.0)) * (0.5 + 0.5 * hr_cov))
    return Segment(kind, s, e, dist, pace, _nanmean(hr), _nanmean(t.ch["cadence_spm"][s:e]),
                   _nanmean(t.ch["grade_pct"][s:e]), gain, _nanmean(t.ch["temperature_c"][s:e]), cv, round(q, 3),
                   first_fin(lat, range(s, e)), first_fin(lon, range(s, e)),
                   first_fin(lat, range(e - 1, s - 1, -1)), first_fin(lon, range(e - 1, s - 1, -1)), label)


def km_splits(t: Telemetry, unit: float = 1000.0) -> list[Segment]:
    d = t.ch["distance_m"]
    out, start, k = [], 0, 1
    for i in range(t.n):
        if d[i] - d[0] >= k * unit:
            out.append(make_segment(t, "split_km", start, i + 1, f"km {k}"))
            start, k = i + 1, k + 1
    return out


def steady_segments(t: Telemetry, min_s: int = 180, max_cv: float = 4.0) -> list[Segment]:
    """Maximal stretches where 60 s rolling pace stays within ±max_cv % of the stretch mean."""
    sp = rolling_nanmean(np.where(t.moving, t.ch["speed_smooth"], np.nan), 30)
    out, i, n = [], 0, t.n
    while i < n:
        if not np.isfinite(sp[i]) or not t.moving[i]:
            i += 1
            continue
        j, s_sum, cnt = i, 0.0, 0
        while j < n and np.isfinite(sp[j]) and t.moving[j]:
            mean = (s_sum + sp[j]) / (cnt + 1)
            if abs(sp[j] - mean) / mean * 100 > max_cv and cnt >= 30:
                break
            s_sum += sp[j]
            cnt += 1
            j += 1
        if j - i >= min_s:
            out.append(make_segment(t, "steady", i, j))
            i = j
        else:
            i += max(1, (j - i) // 2)
    return out


def intervals(t: Telemetry) -> tuple[list[Segment], list[Segment]]:
    """Work/recovery detection: Otsu threshold on 15 s smoothed moving speed; requires a clearly
    bimodal speed distribution and >= 3 work bouts of 30 s – 20 min."""
    sp = rolling_nanmean(t.ch["speed_ms"], 15)
    v = sp[np.isfinite(sp) & (sp > 0.5)]
    if v.size < 300 or np.ptp(v) < 0.3:  # too short, or no meaningful speed variation
        return [], []
    hist, edges = np.histogram(v, bins=60)
    centers = (edges[:-1] + edges[1:]) / 2
    best, thr = -1.0, None
    for k in range(1, 60):
        w0, w1 = hist[:k].sum(), hist[k:].sum()
        if not w0 or not w1:
            continue
        m0 = (hist[:k] * centers[:k]).sum() / w0
        m1 = (hist[k:] * centers[k:]).sum() / w1
        var = w0 * w1 * (m0 - m1) ** 2
        if var > best:
            best, thr, lo_m, hi_m = var, edges[k], m0, m1
    if thr is None or hi_m / lo_m < 1.15:
        return [], []
    work = np.nan_to_num(sp) >= thr
    bouts, i = [], 0
    while i < t.n:
        if work[i]:
            j = i
            while j < t.n and work[j]:
                j += 1
            if 30 <= j - i <= 1200:
                bouts.append((i, j))
            i = j
        else:
            i += 1
    if len(bouts) < 3:
        return [], []
    reps = [make_segment(t, "interval", s, e, f"rep {k+1}") for k, (s, e) in enumerate(bouts)]
    recs = [make_segment(t, "recovery", a[1], b[0], f"recovery {k+1}") for k, (a, b) in enumerate(zip(bouts, bouts[1:]))
            if b[0] - a[1] >= 10]
    return reps, recs
