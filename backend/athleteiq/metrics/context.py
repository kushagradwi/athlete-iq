"""Inputs every calculator sees: telemetry, resolved athlete thresholds, history, caches."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from ..ingestion.normalize import Telemetry


class NA(Exception):
    """Raised by a calculator that cannot produce a value."""

    def __init__(self, state: str, reason: str):
        super().__init__(reason)
        self.state, self.reason = state, reason


@dataclass
class Out:
    value: float | None
    detail: dict = field(default_factory=dict)
    estimated: bool = False  # depends on an estimated threshold or model
    quality: float | None = None


@dataclass
class Thresholds:
    max_hr: float
    rest_hr: float
    lthr: float
    threshold_pace_s_km: float
    ftp_w: float | None
    weight_kg: float
    estimated: set = field(default_factory=set)

    @property
    def threshold_speed(self) -> float:
        return 1000.0 / self.threshold_pace_s_km


@dataclass
class PriorActivity:
    activity_id: str
    start_time: dt.datetime
    sport: str
    distance_m: float
    moving_s: int
    metrics: dict  # metric_id -> value (CALCULATED/ESTIMATED only)
    summary: dict  # pd_curve, holds, aerobic_longest, indexes, steady
    segments: list = field(default_factory=list)  # effort segment dicts (steady/split_km/interval)


@dataclass
class Ctx:
    t: Telemetry
    th: Thresholds
    history: list[PriorActivity] = field(default_factory=list)  # strictly before this activity, same athlete
    cache: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)  # metric_id -> Out, filled as the engine runs

    def need(self, *fields, min_frac=0.2):
        for f in fields:
            if not self.t.has(f, min_frac):
                raise NA("INSUFFICIENT_DATA", f"{f} not recorded")

    def need_moving(self, seconds: int):
        if self.t.moving_s < seconds:
            raise NA("INSUFFICIENT_DATA", f"needs ≥ {seconds} s moving")

    def mv(self, f: str) -> np.ndarray:
        a = self.t.ch[f][self.t.moving]
        return a[np.isfinite(a)]

    def prior(self, sport_only=True, days: int | None = None) -> list[PriorActivity]:
        out = [p for p in self.history if (not sport_only or p.sport == self.t.sport)]
        if days is not None:
            cut = self.t.start_time - dt.timedelta(days=days)
            out = [p for p in out if p.start_time >= cut]
        return out

    def value(self, metric_id: str):
        r = self.results.get(metric_id)
        return r.value if r is not None else None
