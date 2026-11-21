"""Five transparent performance indexes, scored against the athlete's own baseline.

score_component = clip(50 + 15·z, 0, 100), z = robust z-score (median/MAD) of this activity's
value against the athlete's previous values of the same metric, sign-flipped where lower is better.
50 = your typical value; 65 ≈ one robust SD better than typical. These are personal descriptors,
not physiological or medical standards."""
from __future__ import annotations

import numpy as np

from .metrics.context import Ctx

VERSION = "index-1.0.0"
MIN_BASELINE = 3

INDEXES = {
    "aerobic_efficiency": {
        "name": "Aerobic Efficiency Index",
        "interpretation": "Speed you get per heartbeat compared with your usual. Above 50 = more efficient than typical.",
        "components": [("running.efficiency_factor", +1, 0.6), ("running.cardiac_cost", -1, 0.4)],
    },
    "durability": {
        "name": "Durability Index",
        "interpretation": "How well pace-to-HR and form held up late in the session versus your usual.",
        "components": [("running.aerobic_decoupling", -1, 0.5), ("running.hr_drift", -1, 0.2),
                       ("execution.finish_strength", +1, 0.15), ("biomechanics.cadence_drift", +1, 0.15)],
    },
    "consistency": {
        "name": "Consistency Index",
        "interpretation": "How evenly you paced and moved compared with your usual.",
        "components": [("running.km_split_cv", -1, 0.4), ("running.pace_cv", -1, 0.3),
                       ("biomechanics.cadence_cv", -1, 0.3)],
    },
    "execution": {
        "name": "Execution Index",
        "interpretation": "Self-referenced execution: rep consistency on interval days, split evenness and "
                          "finish on continuous runs. No planned-workout targets are used in this version.",
        "components": [("execution.rep_pace_cv", -1, 0.35), ("execution.rep_fade", -1, 0.15),
                       ("running.negative_split_ratio", -1, 0.25), ("execution.finish_strength", +1, 0.25)],
    },
    "progression": {
        "name": "Progression Index",
        "interpretation": "Whether recent trends are moving in your favour: efficiency trend, pace-duration records "
                          "and pace at reference heart rate.",
        "components": [("progression.ef_trend_28d", +1, 0.4), ("progression.pace_duration_prs", +1, 0.3),
                       ("progression.pace_at_reference_hr", -1, 0.3)],
    },
}


def robust_z(x, sample):
    s = np.asarray(sample, float)
    med = float(np.median(s))
    mad = float(np.median(np.abs(s - med)) * 1.4826)
    if mad < 1e-9:
        sd = float(np.std(s))
        mad = sd if sd > 1e-9 else max(abs(med) * 0.02, 1e-6)  # floor: 2% of median
    return (x - med) / mad, med, mad


def compute(ctx: Ctx, metric_values: dict) -> dict:
    """metric_values: current metric_id -> value. History comes from ctx.history[].metrics."""
    out = {}
    prior = ctx.prior()
    for iid, spec in INDEXES.items():
        comps, wsum, ssum, ns = [], 0.0, 0.0, []
        for mid, sign, w in spec["components"]:
            cur = metric_values.get(mid)
            hist = [p.metrics[mid] for p in prior if p.metrics.get(mid) is not None]
            entry = {"metric_id": mid, "weight": w, "direction": "higher is better" if sign > 0 else "lower is better",
                     "value": cur, "baseline_n": len(hist)}
            if cur is None:
                entry["state"] = "INSUFFICIENT_DATA"
            elif len(hist) < MIN_BASELINE:
                entry["state"] = "INSUFFICIENT_DATA"
                entry["reason"] = f"needs ≥ {MIN_BASELINE} previous values"
            else:
                z, med, mad = robust_z(cur, hist)
                score = float(np.clip(50 + 15 * sign * z, 0, 100))
                entry.update(state="CALCULATED", baseline_median=med, baseline_mad=mad, z=float(z), score=score)
                wsum += w
                ssum += w * score
                ns.append(len(hist))
            comps.append(entry)
        total_w = sum(c[2] for c in spec["components"])
        if wsum == 0:
            out[iid] = {"index_id": iid, "name": spec["name"], "score": None, "state": "INSUFFICIENT_DATA",
                        "confidence": 0.0, "components": comps, "version": VERSION,
                        "interpretation": spec["interpretation"]}
            continue
        coverage = wsum / total_w
        n_factor = min(1.0, np.median(ns) / 10)
        conf = float(round(coverage * n_factor * ctx.t.quality.get("score", 1.0), 3))
        out[iid] = {"index_id": iid, "name": spec["name"], "score": round(ssum / wsum, 1),
                    "state": "CALCULATED" if coverage >= 0.5 else "ESTIMATED", "confidence": conf,
                    "components": comps, "version": VERSION, "interpretation": spec["interpretation"],
                    "formula": "Σ wᵢ·clip(50 + 15·signᵢ·zᵢ, 0, 100) / Σ wᵢ over available components"}
    return out
