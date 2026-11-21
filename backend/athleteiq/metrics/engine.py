"""Runs registered calculators and returns structured results with explicit states."""
from __future__ import annotations

import math
import traceback
from dataclasses import dataclass, field

from .calculators import CALCULATORS
from .context import NA, Ctx, Out
from .registry import load_all


@dataclass
class MetricResult:
    metric_id: str
    value: float | None
    unit: str
    state: str
    source: str
    quality: float | None
    algorithm_version: str
    detail: dict = field(default_factory=dict)

    def to_dict(self):
        return self.__dict__.copy()


def _applies(defn, sport):
    return defn.sport in ("general", sport) or (defn.sport == "running" and sport == "running")


def run(ctx: Ctx, phase: str = "main") -> dict[str, MetricResult]:
    """phase "main": activity + history metrics; phase "post": post_discovery metrics."""
    reg = load_all()
    out = {}
    for d in reg.values():
        if not d.implemented:
            continue
        if (phase == "main") == (d.calculation_method == "post_discovery"):
            continue
        if not _applies(d, ctx.t.sport):
            out[d.metric_id] = MetricResult(d.metric_id, None, d.unit, "NOT_APPLICABLE", "calculated", None,
                                            d.algorithm_version, {"reason": f"{d.sport} metric"})
            continue
        try:
            r: Out = CALCULATORS[d.metric_id](ctx)
            v = r.value
            if v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v)):
                raise NA("INVALID_INPUT", "calculation produced a non-finite value")
            state = "ESTIMATED" if r.estimated else "CALCULATED"
            if v is None:
                state = "INSUFFICIENT_DATA"
            ctx.results[d.metric_id] = r
            q = r.quality if r.quality is not None else ctx.t.quality.get("score")
            out[d.metric_id] = MetricResult(d.metric_id, None if v is None else float(v), d.unit, state, "calculated",
                                            q, d.algorithm_version, _clean(r.detail))
        except NA as e:
            out[d.metric_id] = MetricResult(d.metric_id, None, d.unit, e.state, "calculated", None,
                                            d.algorithm_version, {"reason": e.reason})
        except Exception as e:  # a bug in one calculator must not sink the analysis
            out[d.metric_id] = MetricResult(d.metric_id, None, d.unit, "INVALID_INPUT", "calculated", None,
                                            d.algorithm_version, {"reason": f"calculator error: {e}",
                                                                  "trace": traceback.format_exc(limit=2)})
    return out


def _clean(d):
    if isinstance(d, dict):
        return {str(k): _clean(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_clean(v) for v in d]
    if isinstance(d, float):
        return d if math.isfinite(d) else None
    if hasattr(d, "item"):
        return _clean(d.item())
    return d
