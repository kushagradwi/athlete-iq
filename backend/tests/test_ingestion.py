import numpy as np
import pytest

from athleteiq.ingestion.normalize import normalize
from athleteiq.ingestion.parsers import ParseError, detect_format, parse
from athleteiq.synthetic import Seg, Spec, generate, write_csv, write_fit, write_gpx, write_tcx

from .helpers import day

BASE = Spec(start=day(0), segments=[Seg(600, 300)], hr_rest=52, cadence_spm=170, temperature_c=12)


@pytest.mark.parametrize("writer,name", [(write_fit, "a.fit"), (write_tcx, "a.tcx"), (write_gpx, "a.gpx"),
                                         (write_csv, "a.csv")])
def test_every_format_round_trips(writer, name):
    recs = generate(BASE)
    t = normalize(parse(name, writer(recs)))
    assert t.sport == "running"
    assert t.n == 600
    assert abs(t.distance_m - 599 * 1000 / 300) < 3  # GPX derives distance from GPS
    assert abs(np.nanmean(t.ch["heart_rate"]) - 158.7) < 0.5
    assert t.moving_s == 600


def test_fit_running_cadence_per_leg_is_doubled_and_device_calories_kept():
    recs = generate(BASE)
    raw = parse("a.fit", write_fit(recs, calories=432))
    t = normalize(raw)
    assert abs(np.nanmean(t.ch["cadence_spm"]) - 170) < 0.6
    assert any(i["code"] == "cadence_per_leg" for i in t.quality["issues"])
    assert raw.session["total_calories"] == 432


def test_format_detection_by_content_not_extension():
    recs = generate(BASE)
    assert detect_format("wrong.txt", write_fit(recs)[:64]) == "fit"
    assert detect_format("x.bin", write_tcx(recs)[:200]) == "tcx"
    with pytest.raises(ParseError):
        detect_format("x.bin", b"hello world")


def test_corrupt_file_is_a_clean_error():
    with pytest.raises(ParseError):
        parse("x.tcx", b"<TrainingCenterDatabase><broken")
    with pytest.raises(ParseError):
        parse("x.csv", b"foo,bar\n1,2\n")


def test_duplicates_and_out_of_order_samples():
    recs = generate(Spec(start=day(0), segments=[Seg(300, 300)], duplicate_every=10))
    n_dupes = len(recs) - len({r["timestamp"] for r in recs})
    recs[50], recs[51] = recs[51], recs[50]
    t = normalize(parse("a.csv", write_csv(recs)))
    codes = {i["code"]: i for i in t.quality["issues"]}
    assert n_dupes > 0 and codes["duplicate_samples"]["count"] == n_dupes
    assert codes["timestamps_out_of_order"]["count"] >= 1
    assert t.n == 300 and t.quality["score"] < 1.0


def test_gps_jump_removed_and_distance_unaffected_when_measured():
    recs = generate(Spec(start=day(0), segments=[Seg(600, 300)], gps_jump_at=[200, 400]))
    t = normalize(parse("a.gpx", write_gpx(recs)))  # GPX: distance derived from GPS
    assert {i["code"]: i for i in t.quality["issues"]}["gps_jumps"]["count"] == 2
    assert abs(t.distance_m - 599 * 1000 / 300) < 5  # jumps did not add 4 km


def test_pause_is_a_gap_not_interpolated():
    recs = generate(Spec(start=day(0), segments=[Seg(300, 300), Seg(60, 0, kind="pause"), Seg(300, 300)]))
    t = normalize(parse("a.csv", write_csv(recs)))
    assert t.gaps == [(299, 61)]
    assert np.isnan(t.ch["heart_rate"][330])  # inside the gap: missing, not invented
    assert not t.moving[330]


def test_unit_errors_corrected_and_reported():
    recs = generate(Spec(start=day(0), segments=[Seg(900, 300)], temperature_c=20))
    for r in recs:
        r["distance_m"] /= 1000  # file in km
        r["temperature_c"] = 68.0  # °F
    t = normalize(parse("a.csv", write_csv(recs)))
    codes = {i["code"] for i in t.quality["issues"]}
    assert {"distance_units_km", "temperature_units_f"} <= codes
    assert abs(t.distance_m - 899 * 1000 / 300) < 1
    assert abs(np.nanmean(t.ch["temperature_c"]) - 20) < 0.01


def test_implausible_heart_rate_removed():
    recs = generate(Spec(start=day(0), segments=[Seg(300, 300)]))
    for r in recs[:20]:
        r["heart_rate"] = 255
    t = normalize(parse("a.csv", write_csv(recs)))
    assert np.isnan(t.ch["heart_rate"][:20]).all()


def test_provenance_marks_derived_and_unavailable():
    recs = generate(Spec(start=day(0), segments=[Seg(300, 300)], hr=False, cadence_spm=None))
    t = normalize(parse("a.gpx", write_gpx(recs)))
    assert t.provenance["distance_m"] == "derived"
    assert t.provenance["heart_rate"] == "unavailable"
    assert t.provenance["power_w"] == "unavailable"
