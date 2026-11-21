"""Metric registry: exactly 305 definitions. Definitions are data; calculators are linked by id."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

STATUSES = ("implemented_validated", "implemented_experimental", "pending", "requires_sensor", "requires_history")
STATES = ("CALCULATED", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "INVALID_INPUT", "ESTIMATED")
CATEGORIES = {
    "running": ("Running pace and heart rate", 30),
    "cycling": ("Cycling performance", 25),
    "swimming": ("Swimming performance", 20),
    "biomechanics": ("Biomechanics", 25),
    "environment": ("Environmental conditions", 15),
    "execution": ("Workout execution", 20),
    "load": ("Training load and fatigue", 25),
    "progression": ("Performance progression", 20),
    "recovery": ("Sleep and recovery", 20),
    "readiness": ("Training readiness", 15),
    "strength": ("Strength performance", 20),
    "risk": ("Injury and movement risk", 15),
    "planning": ("Training planning", 15),
    "cross": ("Cross-workout performance relationships", 20),
    "discovery": ("AI discovery and confidence", 20),
}
TOTAL = 305


@dataclass
class MetricDefinition:
    metric_id: str
    name: str
    category: str
    sport: str
    description: str
    formula: str
    required_inputs: list[str]
    unit: str
    status: str
    aggregation_method: str = "per_activity"
    supported_timeframes: list[str] = field(default_factory=lambda: ["activity"])
    calculation_method: str = "activity"  # activity | history | post_discovery | external
    algorithm_version: str = "1.0.0"
    validation_rules: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    confidence_requirements: str = "Requires the listed inputs on ≥20% of samples."
    implemented: bool = False

    def to_dict(self):
        d = asdict(self)
        d["category_name"] = CATEGORIES[self.category][0]
        return d


REGISTRY: dict[str, MetricDefinition] = {}


def M(category, metric_id, name, unit, description, formula, inputs, status, sport=None, **kw):
    assert status in STATUSES, status
    assert metric_id not in REGISTRY, f"duplicate {metric_id}"
    if "validation_rules" not in kw:
        kw["validation_rules"] = _default_rules(unit)
    d = MetricDefinition(metric_id=metric_id, name=name, category=category,
                         sport=sport or {"running": "running", "cycling": "cycling", "swimming": "swimming",
                                         "strength": "strength"}.get(category, "general"),
                         description=description, formula=formula, required_inputs=list(inputs), unit=unit,
                         status=status, **kw)
    REGISTRY[metric_id] = d
    return d


def _default_rules(unit):
    return {"bpm": ["30 ≤ value ≤ 240"], "s/km": ["120 ≤ value ≤ 1200"], "%": ["finite"], "s": ["value ≥ 0"],
            "m": ["value ≥ 0"], "spm": ["60 ≤ value ≤ 260"], "W": ["0 ≤ value ≤ 2500"]}.get(unit, ["finite"])


def load_all():
    if not REGISTRY:
        from .definitions import (cat_activity, cat_history, cat_other_sports)  # noqa: F401
        from . import calculators
        for mid in calculators.CALCULATORS:
            if mid not in REGISTRY:
                raise RuntimeError(f"calculator for unregistered metric {mid}")
            REGISTRY[mid].implemented = True
        check()
    return REGISTRY


def check():
    counts = {}
    for d in REGISTRY.values():
        counts[d.category] = counts.get(d.category, 0) + 1
        if d.status in ("implemented_validated", "implemented_experimental") and not d.implemented:
            raise RuntimeError(f"{d.metric_id} marked {d.status} but has no calculator")
    for cat, (_, n) in CATEGORIES.items():
        if counts.get(cat, 0) != n:
            raise RuntimeError(f"category {cat}: {counts.get(cat, 0)} definitions, expected {n}")
    if len(REGISTRY) != TOTAL:
        raise RuntimeError(f"registry has {len(REGISTRY)} definitions, expected {TOTAL}")


def coverage() -> dict:
    reg = load_all()
    by_status, by_cat = {}, {}
    for d in reg.values():
        by_status[d.status] = by_status.get(d.status, 0) + 1
        c = by_cat.setdefault(d.category, {"name": CATEGORIES[d.category][0], "total": 0, "implemented": 0})
        c["total"] += 1
        c["implemented"] += int(d.implemented)
    return {"total": len(reg), "implemented": sum(d.implemented for d in reg.values()),
            "by_status": by_status, "by_category": by_cat}
