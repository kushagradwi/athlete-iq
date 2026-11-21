from athleteiq import indexes
from athleteiq.synthetic import Seg, Spec

from .helpers import analyse, day, history_of


def run(n, pace=330, minutes=30, fitness=1.0):
    return Spec(start=day(n), segments=[Seg(minutes * 60, pace)], fitness=fitness, hr_rest=52, cadence_spm=170,
                noise=0.3, seed=n)


def test_pace_duration_prs():
    hist = history_of([run(0, 330), run(2, 330)])
    r = analyse(run(4, 300), hist)["results"]["progression.pace_duration_prs"]
    # faster everywhere: every duration up to 30 min with prior values is a record (1,2,5,10,20,30 min)
    assert r.state == "CALCULATED" and r.value == 6
    r = analyse(run(4, 360), hist)["results"]["progression.pace_duration_prs"]
    assert r.value == 0


def test_history_metrics_need_history():
    r = analyse(run(0))["results"]
    for mid in ("load.atl", "load.acwr", "progression.ef_trend_28d", "readiness.days_since_last_activity"):
        assert r[mid].state == "INSUFFICIENT_DATA", mid


def test_atl_ctl_and_acwr_from_daily_loads():
    hist = history_of([run(i) for i in range(0, 28, 2)])
    r = analyse(run(28), hist)["results"]
    assert r["load.ctl"].value > 0 and r["load.atl"].value > r["load.ctl"].value  # recent block above long-term
    acwr = r["load.acwr"].value
    assert 0.8 < acwr < 1.6  # steady every-other-day pattern
    assert r["readiness.days_since_last_activity"].value == 2


def test_ef_trend_positive_when_fitness_improves():
    hist = history_of([run(i * 3, fitness=1 + 0.01 * i) for i in range(8)])
    r = analyse(run(24, fitness=1.08), hist)["results"]["progression.ef_trend_28d"]
    assert r.state == "CALCULATED" and r.value > 0 and r.detail["ci95_per_week"][0] > 0


def test_indexes_insufficient_then_scored():
    out = analyse(run(0))
    assert all(v["state"] == "INSUFFICIENT_DATA" and v["score"] is None for v in out["indexes"].values())
    hist = history_of([run(i) for i in range(0, 10, 2)])
    out = analyse(run(12, fitness=1.06), hist)
    aei = out["indexes"]["aerobic_efficiency"]
    assert aei["state"] == "CALCULATED" and aei["score"] > 60  # clearly better than own baseline
    assert 0 < aei["confidence"] <= 1 and aei["version"] == indexes.VERSION
    assert all("baseline_n" in c for c in aei["components"])


def test_index_formula():
    z, med, mad = indexes.robust_z(12, [8, 10, 12, 9, 11])  # MAD = 1
    assert med == 10 and abs(z - 2 / (1 * 1.4826)) < 1e-9
