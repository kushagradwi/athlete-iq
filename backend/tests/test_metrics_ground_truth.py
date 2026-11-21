"""Ground truth for every metric marked implemented_validated.

Expected values are derived analytically from the synthetic generator's physics (noise = 0), not by
re-running the implementation. EXPECTED + VALIDATED_ELSEWHERE must cover every validated metric
(enforced by test_every_validated_metric_has_ground_truth)."""
import math

import pytest

from athleteiq.synthetic import Seg, Spec

from .helpers import analyse, day

HR = round(52 + 32 * (1000 / 300), 1)  # generator HR at 300 s/km (fitness 1, rest 52), recorded to 0.1 bpm → 158.7
HRR = (HR - 52) / (192 - 52)
TRIMP = 60 * HRR * 0.64 * math.exp(1.92 * HRR)
R_LT = (172 - 52) / 140
HRTSS = TRIMP / (60 * R_LT * 0.64 * math.exp(1.92 * R_LT)) * 100
DIST = 3599 * 1000 / 300

STEADY = Spec(start=day(0), segments=[Seg(3600, 300)], hr_rest=52, cadence_spm=170, temperature_c=15)

# metric_id -> (expected, absolute tolerance)
EXPECTED_STEADY = {
    "running.distance": (DIST, 0.5),
    "running.moving_time": (3600, 0),
    "running.elapsed_time": (3600, 0),
    "running.avg_pace": (3600 / (DIST / 1000), 0.05),
    "running.avg_speed": (DIST / 3600, 0.001),
    "running.max_speed_5s": (1000 / 300, 0.001),
    "running.avg_heart_rate": (HR, 0.01),
    "running.max_heart_rate": (HR, 0.01),
    "running.hr_drift": (0, 0.01),
    "running.aerobic_decoupling": (0, 0.01),
    "running.efficiency_factor": (200 / HR, 0.001),
    "running.normalized_graded_pace": (300, 0.1),
    "running.pace_cv": (0, 0.01),
    "running.km_split_cv": (0, 0.5),
    "running.negative_split_ratio": (1.0, 0.003),
    "running.fastest_km": (300, 2),
    "running.slowest_km": (300, 2),
    "running.best_1km": (300, 1),
    "running.best_5km": (1500, 1),
    "running.best_10km": (3000, 1),
    "running.best_pace_5min": (300, 0.01),
    "running.best_pace_20min": (300, 0.01),
    "running.cardiac_cost": (HR * 3600 / 60 / (DIST / 1000), 0.1),
    "running.time_hr_z1": (0, 0), "running.time_hr_z2": (0, 0), "running.time_hr_z3": (3600, 0),
    "running.time_hr_z4": (0, 0), "running.time_hr_z5": (0, 0),
    "running.longest_steady_segment": (3600, 10),
    "biomechanics.avg_cadence": (170, 0.01),
    "biomechanics.cadence_cv": (0, 0.01),
    "biomechanics.cadence_drift": (0, 0.01),
    "biomechanics.avg_stride_length": ((1000 / 300) * 60 / 170, 0.001),
    "biomechanics.total_steps": (170 * 60, 1),
    "biomechanics.cadence_final_quarter": (170, 0.01),
    "environment.avg_temperature": (15, 0.01),
    "environment.max_temperature": (15, 0.01),
    "environment.elevation_gain": (0, 0.01),
    "environment.elevation_loss": (0, 0.01),
    "environment.climb_rate": (0, 0.01),
    "environment.max_altitude": (50, 0.2),
    "execution.interval_count": (0, 0),
    "execution.pause_count": (0, 0),
    "execution.paused_time": (0, 0),
    "execution.moving_ratio": (1.0, 0),
    "execution.data_quality": (1.0, 0.001),
    "execution.finish_strength": ((1000 / 300) / (DIST / 3600), 0.001),
    "load.trimp_banister": (TRIMP, 0.05),
    "load.trimp_edwards": (240, 0.01),  # 0.826·HRmax → band 4 × 60 min
    "load.hrtss": (HRTSS, 0.05),
    "load.rtss": (81.0, 0.1),  # IF 0.9 for 1 h
    "load.intensity_factor": (0.9, 0.0005),
    "load.time_above_lthr": (0, 0),
    "load.session_load": (81.0, 0.1),
    "load.low_intensity_share": (0, 0.01),
    "load.high_intensity_share": (0, 0.01),
}

# Drift: HR rises 10 bpm/h at constant pace
DRIFT = Spec(start=day(1), segments=[Seg(3600, 300)], hr_rest=52, hr_drift_bpm_per_h=10, cadence_spm=170)
HR0 = 52 + 32 * (1000 / 300)
h1, h2 = HR0 + 10 * 899.5 / 3600, HR0 + 10 * 2699.5 / 3600
EXPECTED_DRIFT = {
    "running.hr_drift": (10 * 1500 / 3600, 0.05),
    "running.aerobic_decoupling": ((1 - h1 / h2) * 100, 0.03),
    "running.max_heart_rate": (HR0 + 10 * 3597 / 3600, 0.06),
}

# Negative split: 25 min at 320 s/km then 25 min at 290 s/km
NEG = Spec(start=day(2), segments=[Seg(1500, 320), Seg(1500, 290)], hr_rest=52)
_d1, _d2 = 1500 * 1000 / 320, 1500 * 1000 / 290
_half = (_d1 + _d2) / 2
_t1 = 1500 + (_half - _d1) * 290 / 1000
EXPECTED_NEG = {"running.negative_split_ratio": ((3000 - _t1) / _t1, 0.003)}

# Intervals: 6 × (3 min @ 4:00, 2 min @ 6:30)
INTERVALS = Spec(start=day(3), segments=[Seg(600, 360)] + [Seg(180, 240), Seg(120, 390)] * 6 + [Seg(300, 360)], hr_rest=52)
EXPECTED_INTERVALS = {"execution.interval_count": (6, 0), "execution.rep_pace_cv": (0, 1.0)}

# Pause: 10 min, 2 min not recorded, 10 min
PAUSE = Spec(start=day(4), segments=[Seg(600, 300), Seg(120, 0, kind="pause"), Seg(600, 300)], hr_rest=52)
EXPECTED_PAUSE = {"execution.pause_count": (1, 0), "execution.paused_time": (120, 2),
                  "execution.moving_ratio": (1200 / 1320, 0.002), "running.moving_time": (1200, 2)}

# Hills: 15 min at +5 % then 15 min at −5 %
HILL = Spec(start=day(5), segments=[Seg(900, 360, 5.0), Seg(900, 330, -5.0)], hr_rest=52)
_up, _down = 900 * 1000 / 360 * 0.05, 900 * 1000 / 330 * 0.05
EXPECTED_HILL = {"environment.elevation_gain": (_up, _up * 0.03), "environment.elevation_loss": (_down, _down * 0.03),
                 "environment.climb_rate": (_up / ((900 * 1000 / 360 + 900 * 1000 / 330) / 1000), 0.8),
                 "environment.max_altitude": (50 + _up, 2.0)}

CASES = [(STEADY, EXPECTED_STEADY, "csv"), (DRIFT, EXPECTED_DRIFT, "csv"), (NEG, EXPECTED_NEG, "csv"),
         (INTERVALS, EXPECTED_INTERVALS, "csv"), (PAUSE, EXPECTED_PAUSE, "csv"), (HILL, EXPECTED_HILL, "csv")]


@pytest.mark.parametrize("spec,expected,fmt", CASES, ids=["steady", "drift", "negsplit", "intervals", "pause", "hill"])
def test_ground_truth(spec, expected, fmt):
    r = analyse(spec, fmt=fmt)["results"]
    for mid, (want, tol) in expected.items():
        got = r[mid]
        assert got.state in ("CALCULATED", "ESTIMATED"), f"{mid}: {got.state} {got.detail}"
        assert abs(got.value - want) <= tol + 1e-9, f"{mid}: got {got.value}, want {want} ± {tol}"


def test_cycling_power_ground_truth():
    import datetime as dt

    from athleteiq.ingestion.normalize import normalize
    from athleteiq.ingestion.parsers import parse_csv
    from athleteiq.metrics import engine
    from athleteiq.metrics.context import Ctx

    from .helpers import TH
    t0 = dt.datetime(2026, 9, 1, 7, tzinfo=dt.timezone.utc)
    lines = ["timestamp,distance,speed,hr,cadence,watts,sport"]
    for i in range(3600):
        lines.append(f"{(t0 + dt.timedelta(seconds=i)).isoformat()},{8 * i},8,140,90,250,cycling")
    t = normalize(parse_csv("\n".join(lines).encode()))
    r = engine.run(Ctx(t=t, th=TH), "main")
    want = {"cycling.avg_power": 250, "cycling.max_power_5s": 250, "cycling.normalized_power": 250,
            "cycling.variability_index": 1.0, "cycling.intensity_factor": 1.0, "cycling.tss": 100,
            "cycling.work_kj": 900, "cycling.best_1min_power": 250, "cycling.best_5min_power": 250,
            "cycling.best_20min_power": 250, "cycling.efficiency_factor": 250 / 140, "cycling.power_hr_decoupling": 0,
            "cycling.avg_cadence": 90, "cycling.avg_speed": 8 * 3599 / 3600}
    for mid, v in want.items():
        assert r[mid].state == "CALCULATED", (mid, r[mid].detail)
        assert abs(r[mid].value - v) < 1e-3 * max(1, abs(v)), (mid, r[mid].value, v)
    assert r["running.avg_pace"].state == "NOT_APPLICABLE" or r["running.avg_pace"].value is not None


# Validated metrics whose ground truth lives in other test modules.
VALIDATED_ELSEWHERE = {
    "progression.pace_duration_prs": "test_history_metrics.py::test_pace_duration_prs",
    **{f"discovery.{k}": "test_discovery.py::test_discovery_summary_metrics" for k in (
        "count", "top_significance", "mean_confidence", "personal_records", "emerging_patterns", "confirmed_trends",
        "anomalies", "new_observations", "baseline_sample_size", "evidence_items", "detectors_run",
        "detectors_abstained", "data_quality_weight", "goal_relevance", "novelty", "actionability")},
}


def test_every_validated_metric_has_ground_truth():
    from athleteiq.metrics.registry import load_all
    covered = set(VALIDATED_ELSEWHERE)
    for _, exp, _ in CASES:
        covered |= set(exp)
    covered |= {m for m in load_all() if m.startswith("cycling.")}  # test_cycling_power_ground_truth
    validated = {m for m, d in load_all().items() if d.status == "implemented_validated"}
    missing = validated - covered
    assert not missing, f"validated metrics without a ground-truth test: {sorted(missing)}"


def test_missing_sensor_stays_missing():
    spec = Spec(start=day(6), segments=[Seg(1800, 300)], hr=False, cadence_spm=None, temperature_c=None)
    r = analyse(spec, fmt="csv")["results"]
    for mid in ("running.avg_heart_rate", "running.efficiency_factor", "load.trimp_banister", "biomechanics.avg_cadence",
                "environment.avg_temperature"):
        assert r[mid].value is None and r[mid].state == "INSUFFICIENT_DATA", mid
    assert r["running.distance"].state == "CALCULATED"
