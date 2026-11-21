"""Format parsers: FIT, TCX, GPX, CSV -> RawActivity (irregular samples, untouched units)."""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

SEMI = 180.0 / 2**31
SUPPORTED = (".fit", ".tcx", ".gpx", ".csv")


class ParseError(ValueError):
    pass


@dataclass
class RawActivity:
    fmt: str
    sport: str = "other"
    sub_sport: str | None = None
    device: str | None = None
    start_time: dt.datetime | None = None
    records: list[dict] = field(default_factory=list)  # each has "timestamp" + canonical-ish fields
    session: dict = field(default_factory=dict)  # device summary values (e.g. total_calories)
    notes: list[str] = field(default_factory=list)


def detect_format(filename: str, head: bytes) -> str:
    name = filename.lower()
    if len(head) >= 12 and head[8:12] == b".FIT":
        return "fit"
    text = head[:2048].decode("utf-8", "ignore").lower()
    if "<trainingcenterdatabase" in text:
        return "tcx"
    if "<gpx" in text:
        return "gpx"
    for ext in SUPPORTED:
        if name.endswith(ext):
            return ext[1:]
    raise ParseError("unrecognised file: expected FIT, TCX, GPX or CSV")


def parse(filename: str, data: bytes) -> RawActivity:
    fmt = detect_format(filename, data[:4096])
    try:
        raw = {"fit": parse_fit, "tcx": parse_tcx, "gpx": parse_gpx, "csv": parse_csv}[fmt](data)
    except ParseError:
        raise
    except Exception as e:  # corrupt files surface as a clean validation error
        raise ParseError(f"could not read {fmt.upper()} file: {e}") from e
    if not raw.records:
        raise ParseError("file contains no telemetry samples")
    return raw


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # drop NaN


def _utc(t):
    if t is None:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _iso(s):
    if not s:
        return None
    try:
        return _utc(dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


SPORT_MAP = {
    "running": "running", "run": "running", "trail_running": "running", "treadmill": "running",
    "cycling": "cycling", "biking": "cycling", "bike": "cycling", "ride": "cycling",
    "swimming": "swimming", "swim": "swimming", "lap_swimming": "swimming",
    "training": "strength", "strength_training": "strength", "fitness_equipment": "strength",
    "soccer": "football", "football": "football", "cricket": "cricket",
}


def norm_sport(s: str | None) -> str:
    if not s:
        return "other"
    return SPORT_MAP.get(str(s).strip().lower().replace(" ", "_"), "other")


# ---------------------------------------------------------------- FIT
def parse_fit(data: bytes) -> RawActivity:
    import fitdecode

    raw = RawActivity("fit")
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.WARN) as fr:
        for frame in fr:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            def g(k):
                return frame.get_value(k, fallback=None) if frame.has_field(k) else None

            if frame.name == "record":
                ts = g("timestamp")
                if ts is None:
                    continue
                cad = _f(g("cadence"))
                if cad is not None and _f(g("fractional_cadence")):
                    cad += _f(g("fractional_cadence"))
                lat, lon = g("position_lat"), g("position_long")
                raw.records.append({
                    "timestamp": _utc(ts),
                    "distance_m": _f(g("distance")),
                    "speed_ms": _f(g("enhanced_speed")) if g("enhanced_speed") is not None else _f(g("speed")),
                    "heart_rate": _f(g("heart_rate")),
                    "cadence": cad,
                    "altitude_m": _f(g("enhanced_altitude")) if g("enhanced_altitude") is not None else _f(g("altitude")),
                    "lat": lat * SEMI if isinstance(lat, (int, float)) else None,
                    "lon": lon * SEMI if isinstance(lon, (int, float)) else None,
                    "power_w": _f(g("power")),
                    "temperature_c": _f(g("temperature")),
                    "vertical_oscillation_mm": _f(g("vertical_oscillation")),
                    "ground_contact_ms": _f(g("stance_time")),
                    "stride_length_m": (_f(g("step_length")) / 1000) if _f(g("step_length")) else None,
                    "respiration_rate": _f(g("enhanced_respiration_rate")) or _f(g("respiration_rate")),
                })
            elif frame.name == "session":
                raw.sport = norm_sport(g("sport")) if g("sport") else raw.sport
                raw.sub_sport = str(g("sub_sport")) if g("sub_sport") else None
                raw.start_time = _utc(g("start_time")) or raw.start_time
                for k in ("total_calories", "total_distance", "total_timer_time", "total_elapsed_time"):
                    if g(k) is not None:
                        raw.session[k] = _f(g(k))
            elif frame.name == "sport" and raw.sport == "other":
                raw.sport = norm_sport(g("sport"))
            elif frame.name == "file_id" and not raw.device:
                prod = g("garmin_product") or g("product")
                manu = g("manufacturer")
                raw.device = " ".join(str(x) for x in (manu, prod) if x) or None
    return raw


# ---------------------------------------------------------------- TCX
def parse_tcx(data: bytes) -> RawActivity:
    from lxml import etree

    root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    raw = RawActivity("tcx")

    def local(el):
        return etree.QName(el).localname

    def find(el, name):
        for c in el.iter():
            if c is not el and isinstance(c.tag, str) and local(c) == name:
                return c
        return None

    def text(el, name):
        c = find(el, name)
        return c.text if c is not None else None

    cal = 0.0
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = local(el)
        if tag == "Activity":
            raw.sport = norm_sport(el.get("Sport"))
        elif tag == "Creator" and raw.device is None:
            raw.device = text(el, "Name")
        elif tag == "Lap":
            raw.start_time = raw.start_time or _iso(el.get("StartTime"))
            c = find(el, "Calories")
            if c is not None and _f(c.text):
                cal += _f(c.text)
        elif tag == "Trackpoint":
            hr_el = find(el, "HeartRateBpm")
            raw.records.append({
                "timestamp": _iso(text(el, "Time")),
                "distance_m": _f(text(el, "DistanceMeters")),
                "speed_ms": _f(text(el, "Speed")),
                "heart_rate": _f(text(hr_el, "Value")) if hr_el is not None else None,
                "cadence": _f(text(el, "RunCadence")) or _f(text(el, "Cadence")),
                "altitude_m": _f(text(el, "AltitudeMeters")),
                "lat": _f(text(el, "LatitudeDegrees")),
                "lon": _f(text(el, "LongitudeDegrees")),
                "power_w": _f(text(el, "Watts")),
            })
    if cal:
        raw.session["total_calories"] = cal
    raw.records = [r for r in raw.records if r["timestamp"]]
    return raw


# ---------------------------------------------------------------- GPX
def parse_gpx(data: bytes) -> RawActivity:
    import gpxpy

    g = gpxpy.parse(data.decode("utf-8", "replace"))
    raw = RawActivity("gpx", device=g.creator)
    for trk in g.tracks:
        if trk.type:
            raw.sport = norm_sport(trk.type)
        for seg in trk.segments:
            for p in seg.points:
                ext = {}
                for e in p.extensions:
                    for c in e.iter():
                        ext[c.tag.split("}")[-1].lower()] = c.text
                raw.records.append({
                    "timestamp": _utc(p.time),
                    "lat": p.latitude, "lon": p.longitude, "altitude_m": p.elevation,
                    "heart_rate": _f(ext.get("hr")), "cadence": _f(ext.get("cad")),
                    "power_w": _f(ext.get("power")), "temperature_c": _f(ext.get("atemp")),
                })
    raw.records = [r for r in raw.records if r["timestamp"]]
    if raw.sport == "other":
        raw.sport = "running"
        raw.notes.append("GPX has no activity type; assumed running")
    return raw


# ---------------------------------------------------------------- CSV
CSV_ALIASES = {
    "secs": ("secs", "seconds", "elapsed", "elapsed_s", "time_s"),
    "timestamp": ("timestamp", "time", "datetime"),
    "km": ("km",),
    "distance_m": ("distance", "distance_m", "dist"),
    "kph": ("kph",),
    "speed_ms": ("speed", "speed_ms"),
    "heart_rate": ("hr", "heart_rate", "heartrate", "bpm"),
    "cadence": ("cad", "cadence", "spm", "cadence_spm"),
    "altitude_m": ("alt", "altitude", "altitude_m", "elevation", "ele"),
    "lat": ("lat", "latitude"),
    "lon": ("lon", "lng", "longitude"),
    "power_w": ("watts", "power", "power_w"),
    "temperature_c": ("temp", "temperature", "temperature_c"),
    "sport": ("sport",),
}


def parse_csv(data: bytes) -> RawActivity:
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", "replace"))))
    if not rows:
        raise ParseError("CSV has no rows")
    cols = {k.strip().lower(): k for k in rows[0] if k}
    pick = {key: cols[n] for key, names in CSV_ALIASES.items() for n in names if n in cols}
    if "secs" not in pick and "timestamp" not in pick:
        raise ParseError("CSV needs a 'secs' or 'timestamp' column")
    raw = RawActivity("csv")
    base = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    if "secs" in pick and "timestamp" not in pick:
        raw.notes.append("CSV has elapsed seconds only; start time unknown")
    for r in rows:
        rec = {}
        if "timestamp" in pick and _iso(r[pick["timestamp"]]):
            rec["timestamp"] = _iso(r[pick["timestamp"]])
        elif "secs" in pick and _f(r[pick["secs"]]) is not None:
            rec["timestamp"] = base + dt.timedelta(seconds=_f(r[pick["secs"]]))
        else:
            continue
        if "km" in pick and _f(r[pick["km"]]) is not None:
            rec["distance_m"] = _f(r[pick["km"]]) * 1000
        elif "distance_m" in pick:
            rec["distance_m"] = _f(r[pick["distance_m"]])
        if "kph" in pick and _f(r[pick["kph"]]) is not None:
            rec["speed_ms"] = _f(r[pick["kph"]]) / 3.6
        elif "speed_ms" in pick:
            rec["speed_ms"] = _f(r[pick["speed_ms"]])
        for k in ("heart_rate", "cadence", "altitude_m", "lat", "lon", "power_w", "temperature_c"):
            if k in pick:
                v = _f(r[pick[k]])
                rec[k] = None if (v == 0 and k in ("heart_rate", "lat", "lon")) else v
        raw.records.append(rec)
        if "sport" in pick and raw.sport == "other":
            raw.sport = norm_sport(r[pick["sport"]])
    if raw.sport == "other":
        raw.sport = "running"
        raw.notes.append("CSV has no sport column; assumed running")
    return raw
