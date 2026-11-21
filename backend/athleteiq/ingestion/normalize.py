"""Canonical 1 Hz telemetry with provenance and data-quality assessment.

Missing data stays missing (NaN internally, NULL in the database)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from .parsers import RawActivity

VERSION = "normalize-1.0.0"
MAX_INTERP_GAP_S = 10
FIELDS = ("distance_m", "lat", "lon", "altitude_m", "speed_ms", "heart_rate", "cadence_spm", "power_w",
          "temperature_c", "vertical_oscillation_mm", "ground_contact_ms", "stride_length_m", "respiration_rate")
GPS_MAX_SPEED = {"running": 12.0, "cycling": 35.0, "swimming": 5.0}
MOVING_SPEED = {"running": 0.8, "cycling": 1.5, "swimming": 0.2}


@dataclass
class Telemetry:
    sport: str
    start_time: dt.datetime
    n: int
    ch: dict  # field -> np.ndarray[float] (NaN = missing)
    moving: np.ndarray
    provenance: dict  # field -> measured|derived|estimated|unavailable
    quality: dict  # score, components, issues
    gaps: list = field(default_factory=list)  # [(start_s, duration_s)]
    device: str | None = None
    session: dict = field(default_factory=dict)

    def has(self, f: str, min_frac: float = 0.2) -> bool:
        a = self.ch.get(f)
        return a is not None and np.isfinite(a).sum() >= min_frac * max(self.n, 1)

    @property
    def distance_m(self) -> float:
        d = self.ch["distance_m"]
        fin = d[np.isfinite(d)]
        return float(fin[-1] - fin[0]) if fin.size else 0.0

    @property
    def moving_s(self) -> int:
        return int(self.moving.sum())


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def rolling_nanmean(a: np.ndarray, w: int) -> np.ndarray:
    """Centred rolling mean ignoring NaN; NaN where the window has no data."""
    v = np.where(np.isfinite(a), a, 0.0)
    c = np.isfinite(a).astype(float)
    k = np.ones(w)
    s = np.convolve(v, k, mode="same")
    n = np.convolve(c, k, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = s / n
    out[n == 0] = np.nan
    return out


def normalize(raw: RawActivity) -> Telemetry:
    issues: list[dict] = []
    recs = [r for r in raw.records if r.get("timestamp") is not None]
    n_in = len(recs)

    # --- timestamps: order, duplicates, backwards jumps
    backwards = sum(1 for a, b in zip(recs, recs[1:]) if b["timestamp"] < a["timestamp"])
    recs.sort(key=lambda r: r["timestamp"])
    dedup, dupes = [], 0
    for r in recs:
        if dedup and r["timestamp"] == dedup[-1]["timestamp"]:
            dupes += 1
            for k, v in r.items():  # merge: fill fields the first copy lacked
                if dedup[-1].get(k) is None and v is not None:
                    dedup[-1][k] = v
            continue
        dedup.append(r)
    recs = dedup
    if backwards:
        issues.append({"code": "timestamps_out_of_order", "count": backwards, "action": "sorted"})
    if dupes:
        issues.append({"code": "duplicate_samples", "count": dupes, "action": "merged"})
    if len(recs) < 2:
        raise ValueError("fewer than two distinct timestamps")

    t0 = raw.start_time if (raw.start_time and raw.start_time <= recs[0]["timestamp"]) else recs[0]["timestamp"]
    t0 = recs[0]["timestamp"] if (recs[0]["timestamp"] - t0).total_seconds() > 3600 else t0
    secs = np.array([(r["timestamp"] - t0).total_seconds() for r in recs])
    n = int(round(secs[-1])) + 1
    if n > 72 * 3600:
        raise ValueError("activity longer than 72 hours; refusing to resample")
    grid = np.arange(n, dtype=float)

    def col(name):
        return np.array([np.nan if r.get(name) is None else float(r[name]) for r in recs])

    sport = raw.sport

    # --- GPS anomalies: implied speed between fixes beyond physical limit
    lat, lon = col("lat"), col("lon")
    ok = np.isfinite(lat) & np.isfinite(lon) & ~((lat == 0) & (lon == 0))
    lat[~ok], lon[~ok] = np.nan, np.nan
    jumps = 0
    idx = np.where(ok)[0]
    if idx.size > 2:
        vmax = GPS_MAX_SPEED.get(sport, 40.0)
        prev = idx[0]
        for i in idx[1:]:
            dtt = max(secs[i] - secs[prev], 1.0)
            if haversine(lat[prev], lon[prev], lat[i], lon[i]) / dtt > vmax:
                lat[i], lon[i] = np.nan, np.nan
                jumps += 1
            else:
                prev = i
    if jumps:
        issues.append({"code": "gps_jumps", "count": jumps, "action": "removed fixes"})

    # --- unit sanity
    spd = col("speed_ms")
    if np.isfinite(spd).any() and np.nanmedian(spd) > GPS_MAX_SPEED.get(sport, 40) and sport != "cycling":
        spd = spd / 3.6
        issues.append({"code": "speed_units_kmh", "action": "divided by 3.6"})
    dist = col("distance_m")
    if np.isfinite(dist).sum() > 10:
        dur = secs[-1] - secs[0]
        if dur > 600 and np.nanmax(dist) < 100 and np.nanmax(dist) / dur < 0.1:
            dist = dist * 1000
            issues.append({"code": "distance_units_km", "action": "multiplied by 1000"})
    temp = col("temperature_c")
    if np.isfinite(temp).any() and 60 < np.nanmedian(temp) < 130:
        temp = (temp - 32) / 1.8
        issues.append({"code": "temperature_units_f", "action": "converted to °C"})
    hr = col("heart_rate")
    bad_hr = np.isfinite(hr) & ((hr < 30) | (hr > 240))
    if bad_hr.any():
        hr[bad_hr] = np.nan
        issues.append({"code": "implausible_heart_rate", "count": int(bad_hr.sum()), "action": "removed"})

    raw_cols = {"distance_m": dist, "lat": lat, "lon": lon, "altitude_m": col("altitude_m"), "speed_ms": spd,
                "heart_rate": hr, "cadence_spm": col("cadence"), "power_w": col("power_w"), "temperature_c": temp,
                "vertical_oscillation_mm": col("vertical_oscillation_mm"), "ground_contact_ms": col("ground_contact_ms"),
                "stride_length_m": col("stride_length_m"), "respiration_rate": col("respiration_rate")}

    # --- recording gaps
    d_secs = np.diff(secs)
    gap_idx = np.where(d_secs > MAX_INTERP_GAP_S)[0]
    gaps = [(int(round(secs[i])), int(round(d_secs[i]))) for i in gap_idx]
    if gaps:
        issues.append({"code": "recording_gaps", "count": len(gaps), "total_s": int(sum(g[1] for g in gaps)),
                       "action": "left empty (not interpolated)"})

    def resample(v):
        m = np.isfinite(v)
        if m.sum() < 2:
            return np.full(n, np.nan)
        out = np.interp(grid, secs[m], v[m], left=np.nan, right=np.nan)
        # blank grid points that fall inside a long gap between valid samples
        sv = secs[m]
        pos = np.searchsorted(sv, grid)
        lo = np.clip(pos - 1, 0, sv.size - 1)
        hi = np.clip(pos, 0, sv.size - 1)
        exact = np.isclose(sv[hi], grid) | np.isclose(sv[lo], grid)
        span = sv[hi] - sv[lo]
        out[(span > MAX_INTERP_GAP_S) & ~exact] = np.nan
        return out

    ch = {k: resample(v) for k, v in raw_cols.items()}
    prov = {k: ("measured" if np.isfinite(raw_cols[k]).sum() >= 2 else "unavailable") for k in raw_cols}

    # --- distance (derive from GPS when not measured)
    if np.isfinite(ch["distance_m"]).sum() < 0.2 * n and np.isfinite(ch["lat"]).sum() >= 0.2 * n:
        la, lo_ = ch["lat"], ch["lon"]
        d = np.zeros(n)
        valid = np.where(np.isfinite(la))[0]
        steps = haversine(la[valid[:-1]], lo_[valid[:-1]], la[valid[1:]], lo_[valid[1:]])
        d[valid[1:]] = np.cumsum(steps)
        d = np.maximum.accumulate(np.where(np.isfinite(la), d, 0))
        ch["distance_m"] = d
        prov["distance_m"] = "derived"
    dm = ch["distance_m"]
    if np.isfinite(dm).any():  # hold through gaps & enforce monotonic
        filled = dm.copy()
        last = np.nan
        for i in range(n):
            if np.isfinite(filled[i]):
                last = filled[i] if not np.isfinite(last) else max(last, filled[i])
                filled[i] = last
            elif np.isfinite(last):
                filled[i] = last
        filled[~np.isfinite(filled)] = 0.0
        ch["distance_m"] = filled

    # --- speed (derive from distance when not measured)
    if np.isfinite(ch["speed_ms"]).sum() < 0.5 * n:
        if prov["distance_m"] != "unavailable":
            ch["speed_ms"] = rolling_nanmean(np.concatenate([[0.0], np.diff(ch["distance_m"])]), 5)
            prov["speed_ms"] = "derived"
    sp = ch["speed_ms"]
    sp_s = rolling_nanmean(sp, 5)
    in_gap = np.zeros(n, bool)
    for s, d_ in gaps:
        in_gap[s + 1:s + d_] = True
    moving = np.nan_to_num(sp_s, nan=0.0) >= MOVING_SPEED.get(sport, 0.8)
    moving &= ~in_gap

    # --- cadence: per-leg -> steps/min for running
    cad = ch["cadence_spm"]
    if sport == "running" and np.isfinite(cad).any() and np.nanmedian(cad[cad > 0]) < 110:
        ch["cadence_spm"] = cad * 2
        issues.append({"code": "cadence_per_leg", "action": "doubled to steps/min"})
    ch["cadence_spm"][ch["cadence_spm"] <= 0] = np.nan

    # --- derived channels
    alt_s = rolling_nanmean(ch["altitude_m"], 15)
    grade = np.full(n, np.nan)
    if np.isfinite(alt_s).sum() > 20:
        a, b = alt_s[:-10], alt_s[10:]
        dd = ch["distance_m"][10:] - ch["distance_m"][:-10]
        with np.errstate(invalid="ignore", divide="ignore"):
            g = np.where(dd > 5, (b - a) / dd * 100, np.nan)
        grade[5:n - 5] = np.clip(g, -40, 40)
        grade = rolling_nanmean(grade, 9)
        prov["grade_pct"] = "derived"
    else:
        prov["grade_pct"] = "unavailable"
    ch["grade_pct"] = grade
    ch["altitude_smooth"] = alt_s
    if prov["stride_length_m"] == "unavailable" and sport == "running" and np.isfinite(ch["cadence_spm"]).any():
        with np.errstate(invalid="ignore", divide="ignore"):
            ch["stride_length_m"] = np.where(moving & (ch["cadence_spm"] > 60), sp_s * 60 / ch["cadence_spm"], np.nan)
        prov["stride_length_m"] = "derived"
    ch["speed_smooth"] = sp_s
    with np.errstate(divide="ignore", invalid="ignore"):
        ch["pace_s_km"] = np.where(moving & (sp_s > 0.5), 1000.0 / sp_s, np.nan)
    prov["pace_s_km"] = "derived" if prov["speed_ms"] != "unavailable" else "unavailable"

    quality = assess_quality(n, n_in, dupes, backwards, jumps, gaps, ch, prov, issues)
    return Telemetry(sport=sport, start_time=t0, n=n, ch=ch, moving=moving, provenance=prov, quality=quality,
                     gaps=gaps, device=raw.device, session=raw.session)


def assess_quality(n, n_in, dupes, backwards, jumps, gaps, ch, prov, issues) -> dict:
    gap_s = sum(g[1] for g in gaps)
    hr = ch["heart_rate"]
    hr_fin = hr[np.isfinite(hr)]
    spikes = int((np.abs(np.diff(hr_fin)) > 15).sum()) if hr_fin.size > 2 else 0
    comps = {
        "timestamp_regularity": max(0.0, 1 - (backwards + dupes) / max(n_in, 1) * 5),
        "gap_fraction": max(0.0, 1 - gap_s / max(n, 1) * 2),
        "gps_integrity": (max(0.0, 1 - jumps / max(np.isfinite(ch["lat"]).sum(), 1) * 20)
                          if prov["lat"] != "unavailable" else None),
        "heart_rate_plausibility": (max(0.0, 1 - spikes / max(hr_fin.size, 1) * 50) if hr_fin.size else None),
        "sensor_coverage": float(np.mean([np.isfinite(ch[k]).mean() for k in ("speed_ms", "heart_rate", "distance_m")])),
    }
    weights = {"timestamp_regularity": 0.15, "gap_fraction": 0.25, "gps_integrity": 0.2,
               "heart_rate_plausibility": 0.2, "sensor_coverage": 0.2}
    num = sum(weights[k] * v for k, v in comps.items() if v is not None)
    den = sum(weights[k] for k, v in comps.items() if v is not None)
    if spikes:
        issues.append({"code": "heart_rate_spikes", "count": spikes, "action": "kept; flagged"})
    sensors = [k for k, v in prov.items() if v == "measured"]
    return {"score": round(num / den, 3) if den else 0.0, "components": {k: (round(v, 3) if v is not None else None)
            for k, v in comps.items()}, "issues": issues, "sensors": sensors, "version": VERSION}
