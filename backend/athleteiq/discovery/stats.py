"""Robust statistics for discoveries: median/IQR, robust z, bootstrap CI, Mann–Kendall, classification."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

CLASSIFICATIONS = ("NEW_OBSERVATION", "PERSONAL_RECORD", "EMERGING_PATTERN", "CONFIRMED_TREND", "ANOMALY")


def robust_z(x: float, sample) -> tuple[float, float, float]:
    s = np.asarray(sample, float)
    med = float(np.median(s))
    mad = float(np.median(np.abs(s - med)) * 1.4826)
    if mad < 1e-9:
        sd = float(np.std(s))
        mad = sd if sd > 1e-9 else max(abs(med) * 0.02, 1e-6)
    return (x - med) / mad, med, mad


def iqr(sample) -> tuple[float, float]:
    s = np.asarray(sample, float)
    return float(np.percentile(s, 25)), float(np.percentile(s, 75))


def bootstrap_diff_ci(x: float, sample, n_boot: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% percentile CI for (x − median(baseline)) by resampling the baseline."""
    s = np.asarray(sample, float)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(s, size=(n_boot, s.size), replace=True), axis=1)
    d = x - meds
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def mann_kendall(values) -> tuple[float, float]:
    """Kendall tau of values vs order, and its two-sided p-value."""
    v = np.asarray(values, float)
    if v.size < 4:
        return 0.0, 1.0
    tau, p = sps.kendalltau(np.arange(v.size), v)
    return (float(tau) if tau == tau else 0.0), (float(p) if p == p else 1.0)


@dataclass
class Evaluation:
    classification: str | None
    n: int
    median: float | None
    iqr: tuple | None
    z: float | None  # in the "better" direction (positive = better)
    rank: int | None  # 1 = best ever among baseline + current
    ci: tuple | None  # bootstrap CI of improvement (better-direction units)
    trend_tau: float | None
    trend_p: float | None
    prior_best: float | None
    improvement_abs: float | None  # current vs median, positive = better
    improvement_vs_best: float | None  # current vs prior best, positive = better

    def to_dict(self):
        d = self.__dict__.copy()
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}


def evaluate(current: float, prior_chrono: list[float], higher_is_better: bool, min_n: int = 1) -> Evaluation:
    """Compare current against comparable prior values (chronological)."""
    n = len(prior_chrono)
    if n < min_n:
        return Evaluation("NEW_OBSERVATION" if n == 0 else None, n, None, None, None, None, None, None, None,
                          None, None, None)
    sgn = 1 if higher_is_better else -1
    s = np.asarray(prior_chrono, float)
    z, med, _ = robust_z(current, s)
    z *= sgn
    better_cnt = int((sgn * (s - current) > 0).sum())
    rank = better_cnt + 1
    prior_best = float(s.max() if higher_is_better else s.min())
    ci = None
    if n >= 3:
        lo, hi = bootstrap_diff_ci(current, s)
        ci = (lo, hi) if sgn > 0 else (-hi, -lo)
    tau = p = None
    if n + 1 >= 6:
        tau, p = mann_kendall(list(s) + [current])
        tau *= sgn
    cls = None
    if tau is not None and p is not None and p < 0.05 and tau > 0 and n + 1 >= 6:
        cls = "CONFIRMED_TREND"
    elif rank == 1 and sgn * (current - prior_best) > 0:
        cls = "PERSONAL_RECORD"
    elif n >= 3 and z > 0.5:
        recent = s[-3:]
        earlier = s[:-3] if n > 3 else s
        if (sgn * (recent - np.median(earlier)) > 0).sum() >= 2:
            cls = "EMERGING_PATTERN"
    if cls is None and n >= 5 and z < -2.5:
        cls = "ANOMALY"
    return Evaluation(cls, n, med, iqr(s) if n >= 2 else None, float(z), rank, ci, tau, p, prior_best,
                      float(sgn * (current - med)), float(sgn * (current - prior_best)))


def confidence(ev: Evaluation, data_quality: float, match_quality: float = 1.0) -> float:
    """0–1. Grows with sample size, shrinks when the bootstrap CI includes zero or data are poor."""
    if ev.n == 0:
        return round(0.3 * data_quality, 3)
    size = 1 - math.exp(-ev.n / 4)
    ci_ok = 1.0 if (ev.ci and ev.ci[0] > 0) else (0.75 if ev.ci is None else 0.55)
    if ev.classification == "CONFIRMED_TREND" and ev.trend_p is not None:
        ci_ok = max(ci_ok, 1 - ev.trend_p)
    if ev.classification == "ANOMALY":
        ci_ok = 0.8
    return round(float(np.clip(size * ci_ok * data_quality * match_quality, 0, 1)), 3)


def magnitude(ev: Evaluation) -> float:
    if ev.z is None:
        return 0.2
    return round(float(math.tanh(abs(ev.z) / 2)), 3)
