"""Runs detectors, ranks candidates, de-duplicates."""
from __future__ import annotations

from ..config import settings
from . import detectors  # noqa: F401  (registers detectors)
from .base import DETECTORS, Abstain, Candidate, DetectorContext

NOVELTY = {"PERSONAL_RECORD": 1.0, "CONFIRMED_TREND": 0.8, "ANOMALY": 0.7, "EMERGING_PATTERN": 0.6,
           "NEW_OBSERVATION": 0.3}
GOALS = ("general", "aerobic_base", "speed", "race_5k", "race_10k", "half", "marathon", "trail")


def weights():
    s = settings()
    w = {"novelty": s.rank_w_novelty, "magnitude": s.rank_w_magnitude, "confidence": s.rank_w_confidence,
         "goal_relevance": s.rank_w_goal, "actionability": s.rank_w_action}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()}


def goal_relevance(c: Candidate, goal: str) -> float:
    if goal in c.goal_tags:
        return 1.0
    if "general" in c.goal_tags or goal == "general":
        return 0.6
    return 0.35


def rank(c: Candidate, goal: str, recent_keys: set) -> None:
    nov = NOVELTY.get(c.classification, 0.3)
    if c.dedupe_key in recent_keys:
        nov *= 0.5  # same kind of finding in the last 14 days is less novel
    comp = {"novelty": round(nov, 3), "magnitude": c.magnitude, "confidence": c.confidence,
            "goal_relevance": goal_relevance(c, goal), "actionability": c.actionability}
    w = weights()
    c.ranking = {**comp, "weights": w}
    c.significance_score = round(sum(w[k] * comp[k] for k in w), 4)


def run(ctx: DetectorContext) -> dict:
    cands, abstained, errors = [], [], []
    for det in DETECTORS:
        try:
            found = det.detect(ctx)
            cands.extend(c for c in found if c.classification)
        except Abstain as e:
            abstained.append({"type": det.type, "reason": str(e)})
        except Exception as e:  # a faulty detector is reported, never fatal
            errors.append({"type": det.type, "error": repr(e)})
    for c in cands:
        rank(c, ctx.athlete_goal, ctx.recent_keys)
    cands.sort(key=lambda c: -c.significance_score)
    seen, uniq = set(), []
    for c in cands:
        if c.dedupe_key in seen:
            continue
        seen.add(c.dedupe_key)
        uniq.append(c)
    m = ctx.stats.get("matches", [])
    return {"discoveries": uniq, "abstained": abstained, "errors": errors, "detectors_run": len(DETECTORS),
            "comparable_matches": len(m), "match_quality": (sum(m) / len(m)) if m else None}
