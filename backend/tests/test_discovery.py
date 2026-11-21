import numpy as np
import pytest

from athleteiq.discovery import stats
from athleteiq.discovery.comparable import Tolerances, geo_close, similarity
from athleteiq.discovery.engine import rank, weights
from athleteiq.synthetic import Seg, Spec

from .helpers import analyse, day, history_of


# ------------------------------------------------------------------ statistics
def test_robust_z_known_values():
    z, med, mad = stats.robust_z(14, [10, 10, 11, 9, 10, 12, 8])
    assert med == 10 and abs(mad - 1.4826) < 1e-9 and abs(z - 4 / 1.4826) < 1e-9


def test_robust_z_ignores_outlier():
    z, med, _ = stats.robust_z(11, [10, 10, 11, 9, 10, 100])
    assert med == 10 and z < 2


def test_bootstrap_ci_contains_true_difference():
    rng = np.random.default_rng(0)
    base = rng.normal(150, 2, 30)
    lo, hi = stats.bootstrap_diff_ci(140, base)  # true difference vs population median: −10
    assert lo < hi < 0
    assert lo - 1 <= -10 <= hi + 1 and hi - lo < 4


def test_mann_kendall_detects_monotonic_trend():
    tau, p = stats.mann_kendall([1, 2, 3, 4, 5, 6, 7, 8])
    assert tau == pytest.approx(1.0) and p < 0.01
    tau, p = stats.mann_kendall([3, 1, 4, 1, 5, 2, 3, 2])
    assert p > 0.05


@pytest.mark.parametrize("prior,current,higher,cls", [
    ([], 5, True, "NEW_OBSERVATION"),
    ([3, 4, 3.5], 5, True, "PERSONAL_RECORD"),
    ([3, 4, 3.5], 3.2, True, None),
    ([1, 2, 3, 4, 5, 6], 7, True, "CONFIRMED_TREND"),
    ([5, 5.1, 4.9, 5, 5.05, 4.95], 1, True, "ANOMALY"),
    ([150, 152, 151], 148, False, "PERSONAL_RECORD"),  # lower is better (HR)
    ([10, 10, 10, 11, 11.5, 10.5], 11.2, True, "EMERGING_PATTERN"),
])
def test_classification_ladder(prior, current, higher, cls):
    assert stats.evaluate(current, prior, higher).classification == cls


def test_single_session_is_never_a_confirmed_trend():
    ev = stats.evaluate(9, [5], True)
    assert ev.classification == "PERSONAL_RECORD"


def test_confidence_grows_with_sample_size():
    small = stats.confidence(stats.evaluate(5, [4], True), 1.0)
    big = stats.confidence(stats.evaluate(5, [4, 4.1, 3.9, 4.0, 4.05, 3.95, 4.02], True), 1.0)
    assert big > small


# ------------------------------------------------------------------ comparable efforts
SEG = {"avg_pace_s_km": 300, "avg_hr": 150, "duration_s": 1200, "avg_grade": 0.0, "temperature_c": 15, "quality": 0.95}


@pytest.mark.parametrize("change,ok", [({}, True), ({"avg_pace_s_km": 312}, False), ({"duration_s": 500}, False),
                                       ({"avg_grade": 2.5}, False), ({"temperature_c": 25}, False),
                                       ({"quality": 0.5}, False), ({"temperature_c": None}, True)])
def test_comparable_tolerances(change, ok):
    assert (similarity(SEG, {**SEG, **change}, Tolerances()) is not None) == ok


def test_geo_close():
    assert geo_close(51.5, -0.12, 51.5002, -0.12)  # ~22 m
    assert not geo_close(51.5, -0.12, 51.501, -0.12)  # ~111 m


# ------------------------------------------------------------------ detectors on synthetic histories
def steady(n, fitness, minutes=40, pace=330, temp=12, hr=True, extra=0):
    return Spec(start=day(n), segments=[Seg(minutes * 60 + extra, pace, 0.0)], fitness=fitness, hr_rest=52,
                cadence_spm=170, temperature_c=temp, noise=0.3, seed=n, hr=hr)


def test_lower_hr_at_same_pace_is_detected_with_evidence():
    hist = history_of([steady(i, 1.0) for i in range(0, 12, 2)])
    out = analyse(steady(14, 1.06), hist)
    ds = {d.type: d for d in out["discoveries"]["discoveries"]}
    d = ds["AEROBIC_EFFICIENCY_GAIN"]
    assert d.classification in ("PERSONAL_RECORD", "CONFIRMED_TREND")
    assert d.observed_value["avg_hr"] < d.baseline_value["median_hr"] - 3
    assert any(e.kind == "activity" for e in d.evidence) and any(e.kind == "statistic" for e in d.evidence)
    assert d.recommended_experiment["success_criterion"]
    assert 0 < d.confidence <= 1 and d.limitations


def test_longest_hold_record_mentions_lower_hr():
    hist = history_of([steady(i, 1.0, minutes=20 + i) for i in range(0, 10, 2)])
    out = analyse(steady(12, 1.05, minutes=45), hist)
    d = next(d for d in out["discoveries"]["discoveries"] if d.type == "PACE_DURABILITY_RECORD")
    assert d.classification in ("PERSONAL_RECORD", "CONFIRMED_TREND") and d.improvement["rank"] == 1
    assert d.observed_value["seconds"] > d.baseline_value["previous_longest_s"]
    assert "lower" in d.description


def test_no_heart_rate_means_hr_detectors_abstain():
    hist = history_of([steady(i, 1.0, hr=False) for i in range(0, 8, 2)])
    out = analyse(steady(10, 1.05, hr=False), hist)
    types = {d.type for d in out["discoveries"]["discoveries"]}
    abst = {a["type"] for a in out["discoveries"]["abstained"]}
    assert "AEROBIC_EFFICIENCY_GAIN" not in types and "AEROBIC_EFFICIENCY_GAIN" in abst
    assert "HEART_RATE_PACE_DEVIATION" in abst


def test_dissimilar_conditions_are_not_compared():
    hist = history_of([steady(i, 1.0, temp=5) for i in range(0, 12, 2)])
    out = analyse(steady(14, 1.08, temp=28), hist)  # 23 °C hotter: no comparable efforts
    assert "AEROBIC_EFFICIENCY_GAIN" not in {d.type for d in out["discoveries"]["discoveries"]}


def test_hr_pace_anomaly_flags_unusually_high_hr():
    specs = [Spec(start=day(i), segments=[Seg(900, p), Seg(900, p - 30)], hr_rest=52, noise=0.3, seed=i)
             for i, p in zip(range(0, 24, 2), [360, 350, 345, 355, 340, 350, 360, 345, 350, 355, 340, 350])]
    hist = history_of(specs)
    sick = Spec(start=day(30), segments=[Seg(900, 350), Seg(900, 320)], hr_rest=70, noise=0.3, seed=99)
    d = [d for d in analyse(sick, hist)["discoveries"]["discoveries"] if d.type == "HEART_RATE_PACE_DEVIATION"]
    assert d and d[0].classification == "ANOMALY"
    assert "not a medical finding" in " ".join(d[0].limitations)


def test_ranking_uses_configured_weights_and_novelty_decay():
    from athleteiq.discovery.base import Candidate
    w = weights()
    assert abs(sum(w.values()) - 1) < 1e-9
    c = Candidate("X", "PERSONAL_RECORD", "t", "d", {}, {}, {}, 0.8, 0.5, 0.7, ["aerobic_base"], [], [], {}, "X:1")
    rank(c, "aerobic_base", set())
    first = c.significance_score
    assert abs(first - (0.2 * 1.0 + 0.25 * 0.5 + 0.25 * 0.8 + 0.15 * 1.0 + 0.15 * 0.7)) < 1e-9
    rank(c, "aerobic_base", {"X:1"})
    assert c.significance_score < first


def test_discovery_summary_metrics():
    """Ground truth for the discovery.* registry metrics (post-discovery pass)."""
    from athleteiq.metrics import engine
    hist = history_of([steady(i, 1.0) for i in range(0, 12, 2)])
    out = analyse(steady(14, 1.06), hist)
    ctx, ds = out["ctx"], out["discoveries"]
    ctx.cache["discovery_summary"] = {
        "discoveries": [{"classification": c.classification, "significance_score": c.significance_score,
                         "confidence": c.confidence, "ranking": c.ranking, "evidence": c.evidence} for c in ds["discoveries"]],
        "detectors_run": ds["detectors_run"], "detectors_abstained": len(ds["abstained"]),
        "comparable_matches": ds["comparable_matches"], "match_quality": ds["match_quality"]}
    r = engine.run(ctx, "post")
    cands = ds["discoveries"]
    v = {k: r[k].value for k in r}
    assert v["discovery.count"] == len(cands)
    assert v["discovery.top_significance"] == max(c.significance_score for c in cands)
    assert v["discovery.mean_confidence"] == pytest.approx(np.mean([c.confidence for c in cands]))
    for cls, key in [("PERSONAL_RECORD", "personal_records"), ("EMERGING_PATTERN", "emerging_patterns"),
                     ("CONFIRMED_TREND", "confirmed_trends"), ("ANOMALY", "anomalies"), ("NEW_OBSERVATION", "new_observations")]:
        assert v[f"discovery.{key}"] == sum(c.classification == cls for c in cands)
    assert v["discovery.baseline_sample_size"] == 6
    assert v["discovery.evidence_items"] == sum(len(c.evidence) for c in cands)
    assert v["discovery.detectors_run"] == 15
    assert v["discovery.detectors_abstained"] == len(ds["abstained"])
    assert v["discovery.data_quality_weight"] == ctx.t.quality["score"]
    for k in ("goal_relevance", "novelty", "actionability"):
        assert v[f"discovery.{k}"] == pytest.approx(np.mean([c.ranking[k] for c in cands]))
