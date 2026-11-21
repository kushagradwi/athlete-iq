"""Discovery contracts and the detector plugin registry."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..metrics.context import Ctx

VERSION = "discovery-1.0.0"
DETECTORS: list = []


def register(cls):
    DETECTORS.append(cls())
    return cls


@dataclass
class Evidence:
    kind: str  # metric|segment|activity|statistic
    label: str
    ref_id: str | None = None
    value: float | None = None
    unit: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class Candidate:
    type: str
    classification: str
    title: str
    description: str
    observed_value: dict
    baseline_value: dict
    improvement: dict
    confidence: float
    magnitude: float
    actionability: float
    goal_tags: list
    evidence: list
    limitations: list
    recommended_experiment: dict
    dedupe_key: str = ""
    discovery_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ranking: dict = field(default_factory=dict)
    significance_score: float = 0.0
    algorithm_version: str = VERSION


@dataclass
class DetectorContext:
    m: Ctx  # metrics context (telemetry, thresholds, history, caches)
    metrics: dict  # metric_id -> value for this activity
    segments: list  # this activity's Segment objects
    athlete_goal: str = "general"
    recent_keys: set = field(default_factory=set)  # dedupe keys of discoveries in the last 14 days
    stats: dict = field(default_factory=dict)  # comparable_matches, match_quality accumulators

    @property
    def quality(self) -> float:
        return float(self.m.t.quality.get("score", 1.0))


class Detector:
    type = "BASE"
    version = "1.0.0"
    actionability = 0.5
    goal_tags: tuple = ()

    def detect(self, ctx: DetectorContext) -> list[Candidate]:
        raise NotImplementedError


class Abstain(Exception):
    """A detector found insufficient evidence; recorded, not an error."""
