"""In-memory analysis (no database) mirroring the pipeline, for metric and detector tests."""
import datetime as dt

from athleteiq import indexes as idx
from athleteiq.discovery import engine as disc_engine
from athleteiq.discovery.base import DetectorContext
from athleteiq.discovery.detectors import aerobic_longest
from athleteiq.ingestion.parsers import parse
from athleteiq.ingestion.normalize import normalize
from athleteiq.metrics import calculators as C
from athleteiq.metrics import engine
from athleteiq.metrics.context import Ctx, PriorActivity, Thresholds
from athleteiq.synthetic import generate, write_fit

UTC = dt.timezone.utc
TH = Thresholds(max_hr=192, rest_hr=52, lthr=172, threshold_pace_s_km=270, ftp_w=250, weight_kg=68)


def day(n, hour=7):
    return dt.datetime(2026, 9, 1, hour, tzinfo=UTC) + dt.timedelta(days=n)


def telemetry(spec, fmt="fit"):
    recs = generate(spec)
    return normalize(parse(f"x.{fmt}", write_fit(recs, spec.sport) if fmt == "fit" else __import__(
        "athleteiq.synthetic", fromlist=["x"]).__dict__[f"write_{fmt}"](recs)))


def analyse(spec, history=None, th=TH, goal="general", fmt="fit"):
    t = telemetry(spec, fmt)
    ctx = Ctx(t=t, th=Thresholds(**{**th.__dict__, "estimated": set(th.estimated)}), history=history or [])
    res = engine.run(ctx, "main")
    values = {k: r.value for k, r in res.items() if r.state in ("CALCULATED", "ESTIMATED")}
    segs = C.splits(ctx) + C.steadies(ctx) + C.reps(ctx)[0] + C.reps(ctx)[1]
    ix = idx.compute(ctx, values)
    ctx.cache["indexes"] = {k: v["score"] for k, v in ix.items()}
    dres = disc_engine.run(DetectorContext(m=ctx, metrics=values, segments=segs, athlete_goal=goal))
    summary = {"pd_curve": C.pd_curve(ctx), "holds": C.hold_bands(ctx), "indexes": ctx.cache["indexes"]}
    if t.has("heart_rate"):
        summary["aerobic_longest"] = aerobic_longest(ctx)[0]
    prior = PriorActivity(activity_id=f"act-{spec.start:%Y%m%d%H%M}", start_time=t.start_time, sport=t.sport,
                          distance_m=t.distance_m, moving_s=t.moving_s, metrics=values, summary=summary,
                          segments=[{"kind": s.kind, "start_s": s.start_s, "duration_s": s.duration_s,
                                     "distance_m": s.distance_m, "avg_pace_s_km": s.avg_pace_s_km, "avg_hr": s.avg_hr,
                                     "avg_grade": s.avg_grade, "temperature_c": s.temperature_c, "quality": s.quality,
                                     "start_lat": s.start_lat, "start_lon": s.start_lon, "end_lat": s.end_lat,
                                     "end_lon": s.end_lon} for s in segs])
    return {"t": t, "ctx": ctx, "results": res, "values": values, "indexes": ix, "discoveries": dres, "prior": prior}


def history_of(specs, th=TH):
    hist = []
    for sp in specs:
        hist.append(analyse(sp, list(hist), th)["prior"])
    return hist
