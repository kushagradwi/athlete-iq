"""Synthetic telemetry with known ground truth, and writers for FIT/TCX/GPX/CSV.

Used by tests (exact expected values) and by the demo athlete. Synthetic data is
always labelled as such; it never stands in for a real athlete's data."""
from __future__ import annotations

import datetime as dt
import math
import random
import struct
from dataclasses import dataclass, field


@dataclass
class Seg:
    duration_s: int
    pace_s_km: float  # 0 = standing still
    grade_pct: float = 0.0
    kind: str = "steady"  # steady|work|rest|pause (pause = no samples recorded)


@dataclass
class Spec:
    start: dt.datetime
    segments: list[Seg]
    sport: str = "running"
    fitness: float = 1.0  # >1 = fitter (lower HR for the same speed)
    hr_rest: float = 55.0
    hr_drift_bpm_per_h: float = 0.0
    cadence_spm: float | None = 170.0
    temperature_c: float | None = None
    noise: float = 0.0  # 0 = exact ground truth
    hr: bool = True
    gps: bool = True
    gps_jump_at: list[int] = field(default_factory=list)  # elapsed seconds with a 2 km jump
    duplicate_every: int = 0  # duplicate every Nth sample
    seed: int = 1
    lat0: float = 51.5
    lon0: float = -0.12


def hr_model(speed_ms, grade, t_s, spec: Spec):
    if speed_ms <= 0:
        return spec.hr_rest + 35
    return spec.hr_rest + 32 * speed_ms / spec.fitness + 2.2 * grade + spec.hr_drift_bpm_per_h * t_s / 3600


def generate(spec: Spec) -> list[dict]:
    """Returns records with 'timestamp' + canonical fields (1 s spacing), HR with first-order lag."""
    rnd = random.Random(spec.seed)
    recs, t, dist, alt, lat, lon, heading = [], 0, 0.0, 50.0, spec.lat0, spec.lon0, 0.3
    hr = None
    for seg in spec.segments:
        for _ in range(seg.duration_s):
            if seg.kind == "pause":
                t += 1
                continue
            speed = 0.0 if seg.pace_s_km <= 0 else 1000.0 / (seg.pace_s_km * (1 + spec.noise * rnd.gauss(0, 0.01)))
            target = hr_model(speed, seg.grade_pct, t, spec)
            hr = target if hr is None else hr + (target - hr) / (15 if spec.noise else 1)
            dist += speed
            alt += speed * seg.grade_pct / 100
            heading += spec.noise * rnd.gauss(0, 0.02)
            lat += speed * math.cos(heading) / 111111
            lon += speed * math.sin(heading) / (111111 * math.cos(math.radians(lat)))
            r = {"timestamp": spec.start + dt.timedelta(seconds=t), "distance_m": dist, "speed_ms": speed,
                 "altitude_m": alt}
            if spec.hr:
                r["heart_rate"] = round(hr + spec.noise * rnd.gauss(0, 1), 1)
            if spec.cadence_spm and speed > 0:
                r["cadence"] = spec.cadence_spm + (speed - 3) * 4 * (spec.noise > 0) + spec.noise * rnd.gauss(0, 1)
            if spec.temperature_c is not None:
                r["temperature_c"] = spec.temperature_c
            if spec.gps:
                jl = 0.02 if t in spec.gps_jump_at else 0.0
                r["lat"], r["lon"] = lat + jl, lon
            recs.append(r)
            if spec.duplicate_every and len(recs) % spec.duplicate_every == 0:
                recs.append(dict(r))
            t += 1
    return recs


# ---------------------------------------------------------------- writers
FIT_EPOCH = dt.datetime(1989, 12, 31, tzinfo=dt.timezone.utc)
_CRC = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def fit_crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC[byte & 0xF]
        tmp = _CRC[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC[(byte >> 4) & 0xF]
    return crc


def _fts(t: dt.datetime) -> int:
    return int((t - FIT_EPOCH).total_seconds())


def write_fit(recs: list[dict], sport: str = "running", calories: int | None = None) -> bytes:
    """Minimal valid FIT activity: file_id, record messages, session. Running cadence written per leg
    (as Garmin devices do)."""
    body = bytearray()

    def define(local, gmn, fields):
        body.extend(struct.pack("<BBBHB", 0x40 | local, 0, 0, gmn, len(fields)))
        for num, size, base in fields:
            body.extend(struct.pack("<BBB", num, size, base))

    # file_id
    define(0, 0, [(0, 1, 0x00), (1, 2, 0x84), (2, 2, 0x84), (4, 4, 0x86)])
    body.extend(struct.pack("<BBHHI", 0, 4, 255, 0, _fts(recs[0]["timestamp"])))
    # record
    define(1, 20, [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (5, 4, 0x86), (6, 2, 0x84), (3, 1, 0x02),
                   (4, 1, 0x02), (2, 2, 0x84), (13, 1, 0x01)])
    for r in recs:
        def u(v, scale=1, off=0, inv=0xFFFFFFFF, lim=None):
            if v is None:
                return inv
            x = int(round((v + off) * scale))
            return max(0, min(x, lim if lim is not None else inv - 1))
        la = int(round(r["lat"] / (180.0 / 2**31))) if r.get("lat") is not None else 0x7FFFFFFF
        lo = int(round(r["lon"] / (180.0 / 2**31))) if r.get("lon") is not None else 0x7FFFFFFF
        cad = r.get("cadence")
        cad = cad / 2 if (cad is not None and sport == "running") else cad
        temp = r.get("temperature_c")
        body.extend(struct.pack("<BIiiIHBBHb", 1, _fts(r["timestamp"]), la, lo,
                                u(r.get("distance_m"), 100), u(r.get("speed_ms"), 1000, inv=0xFFFF),
                                u(r.get("heart_rate"), inv=0xFF), u(cad, inv=0xFF),
                                u(r.get("altitude_m"), 5, 500, inv=0xFFFF),
                                0x7F if temp is None else int(round(temp))))
    # session
    define(2, 18, [(253, 4, 0x86), (2, 4, 0x86), (5, 1, 0x00), (7, 4, 0x86), (9, 4, 0x86), (11, 2, 0x84)])
    sp = {"running": 1, "cycling": 2, "swimming": 5}.get(sport, 0)
    el = (recs[-1]["timestamp"] - recs[0]["timestamp"]).total_seconds()
    body.extend(struct.pack("<BIIBIIH", 2, _fts(recs[-1]["timestamp"]), _fts(recs[0]["timestamp"]), sp,
                            int(el * 1000), int((recs[-1].get("distance_m") or 0) * 100),
                            calories if calories is not None else 0xFFFF))
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", fit_crc(header))
    data = header + bytes(body)
    return data + struct.pack("<H", fit_crc(data))


def write_tcx(recs, sport="Running") -> bytes:
    out = ['<?xml version="1.0" encoding="UTF-8"?><TrainingCenterDatabase '
           'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities>'
           f'<Activity Sport="{sport}"><Id>{recs[0]["timestamp"].isoformat()}</Id>'
           f'<Lap StartTime="{recs[0]["timestamp"].isoformat()}"><Track>']
    for r in recs:
        p = [f"<Trackpoint><Time>{r['timestamp'].isoformat()}</Time>"]
        if r.get("lat") is not None:
            p.append(f"<Position><LatitudeDegrees>{r['lat']:.7f}</LatitudeDegrees>"
                     f"<LongitudeDegrees>{r['lon']:.7f}</LongitudeDegrees></Position>")
        if r.get("altitude_m") is not None:
            p.append(f"<AltitudeMeters>{r['altitude_m']:.2f}</AltitudeMeters>")
        p.append(f"<DistanceMeters>{r['distance_m']:.2f}</DistanceMeters>")
        if r.get("heart_rate") is not None:
            p.append(f"<HeartRateBpm><Value>{round(r['heart_rate'])}</Value></HeartRateBpm>")
        if r.get("cadence") is not None:
            p.append(f"<Cadence>{round(r['cadence'] / 2)}</Cadence>")
        p.append("</Trackpoint>")
        out.append("".join(p))
    out.append("</Track></Lap></Activity></Activities></TrainingCenterDatabase>")
    return "".join(out).encode()


def write_gpx(recs) -> bytes:
    out = ['<?xml version="1.0"?><gpx version="1.1" creator="athleteiq-synthetic" '
           'xmlns="http://www.topografix.com/GPX/1/1" '
           'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><type>running</type><trkseg>']
    for r in recs:
        if r.get("lat") is None:
            continue
        ext = f"<gpxtpx:hr>{round(r['heart_rate'])}</gpxtpx:hr>" if r.get("heart_rate") is not None else ""
        out.append(f'<trkpt lat="{r["lat"]:.7f}" lon="{r["lon"]:.7f}"><ele>{r.get("altitude_m", 0):.2f}</ele>'
                   f'<time>{r["timestamp"].isoformat().replace("+00:00", "Z")}</time>'
                   f'<extensions><gpxtpx:TrackPointExtension>{ext}</gpxtpx:TrackPointExtension></extensions></trkpt>')
    out.append("</trkseg></trk></gpx>")
    return "".join(out).encode()


def write_csv(recs) -> bytes:
    lines = ["timestamp,distance_m,speed_ms,hr,cadence,altitude_m,lat,lon,temperature"]
    for r in recs:
        def v(k):
            x = r.get(k)
            return "" if x is None else f"{x}"
        lines.append(",".join([r["timestamp"].isoformat(), v("distance_m"), v("speed_ms"), v("heart_rate"),
                               v("cadence"), v("altitude_m"), v("lat"), v("lon"), v("temperature_c")]))
    return "\n".join(lines).encode()
