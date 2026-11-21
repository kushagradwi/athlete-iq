"""End-to-end through the HTTP API (SQLite, inline jobs)."""
from fastapi.testclient import TestClient

from athleteiq.synthetic import Seg, Spec, generate, write_fit

from .helpers import day


def test_upload_to_discovery_journey(db):
    from athleteiq.api.main import app
    c = TestClient(app)
    a = c.post("/api/v1/athletes", json={"name": "T", "max_hr": 192, "rest_hr": 52, "lthr": 172}).json()
    jobs = []
    for i in range(5):
        spec = Spec(start=day(i * 2), segments=[Seg(2400, 330)], fitness=1 + 0.02 * i, hr_rest=52, noise=0.3, seed=i)
        r = c.post("/api/v1/activities/upload", data={"athlete_id": a["athlete_id"]},
                   files={"file": (f"r{i}.fit", write_fit(generate(spec)))})
        assert r.status_code == 202, r.text
        jobs.append(r.json())
    j = c.get(f"/api/v1/analysis/{jobs[-1]['job_id']}").json()
    assert j["status"] == "done", j
    aid = j["activity_id"]
    assert c.get(f"/api/v1/activities/{aid}").json()["status"] == "analysed"
    assert len(c.get(f"/api/v1/activities/{aid}/metrics").json()["metrics"]) == 305
    assert c.get(f"/api/v1/activities/{aid}/charts").json()["series"]["pace_s_km"]
    d = c.get(f"/api/v1/activities/{aid}/discoveries").json()
    assert d["top"] and all(x["evidence"] for x in d["top"]) and d["commentary"]
    # idempotent re-upload
    dup = c.post("/api/v1/activities/upload", data={"athlete_id": a["athlete_id"]},
                 files={"file": ("again.fit", write_fit(generate(Spec(start=day(8), segments=[Seg(2400, 330)],
                                                                      fitness=1.08, hr_rest=52, noise=0.3, seed=4))))})
    assert dup.json()["duplicate"] is True
    bad = c.post("/api/v1/activities/upload", data={"athlete_id": a["athlete_id"]}, files={"file": ("x.bin", b"nope")})
    assert bad.status_code == 422
    ans = c.post(f"/api/v1/athletes/{a['athlete_id']}/ask", json={"question": "Have I improved aerobic efficiency?"}).json()
    assert ans["claims"] and ans["validation"]["rejected"] == 0
    assert c.get("/api/v1/metrics/registry").json()["total"] == 305
    assert c.get("/api/v1/metrics/coverage").json()["implemented"] >= 35


def test_ai_validation_drops_uncited_and_invented_numbers():
    from athleteiq.ai.service import validate
    resp = {"answer": "x", "insufficient_evidence": False, "claims": [
        {"text": "Your HR was 150 bpm.", "evidence_ids": ["d1"]},
        {"text": "Your HR was 133 bpm.", "evidence_ids": ["d1"]},
        {"text": "Great run.", "evidence_ids": ["nope"]}]}
    out, rep = validate(resp, {"d1"}, [150.0])
    assert [c["text"] for c in out["claims"]] == ["Your HR was 150 bpm."] and rep["rejected"] == 2
