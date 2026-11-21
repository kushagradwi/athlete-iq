"""GoldenCheetah adapter. GoldenCheetah is an external desktop application:

* Import: GoldenCheetah has no upload API. We copy the ORIGINAL file into an auto-import folder
  (GoldenCheetah: Athlete settings → Auto Import) when GC_AUTOIMPORT_DIR is configured.
* Read: GoldenCheetah's local REST API (Preferences → General → "Enable API Web Services",
  default http://localhost:12021) is read-only. GET /<athlete> returns a CSV activity list with
  metric columns; we match by start time and compare overlapping metrics with our own values.

The application never depends on GoldenCheetah: every failure is recorded and analysis continues."""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import urllib.parse

import httpx

from ..config import settings

VERSION = "gc-adapter-1.0.0"

# GoldenCheetah metric column -> (our metric_id, converter to our unit)
COMPARABLE = {
    "Distance": ("running.distance", lambda v: v * 1000),  # km -> m
    "Duration": ("running.elapsed_time", lambda v: v),  # s
    "Time Moving": ("running.moving_time", lambda v: v),
    "Average Heart Rate": ("running.avg_heart_rate", lambda v: v),
    "Max Heartrate": ("running.max_heart_rate", lambda v: v),
    "Elevation Gain": ("environment.elevation_gain", lambda v: v),
    "TRIMP Points": ("load.trimp_banister", lambda v: v),
    "Average Running Cadence": ("biomechanics.avg_cadence", lambda v: v),
}


class GoldenCheetah:
    def __init__(self, base_url=None, athlete=None, autoimport_dir=None, client: httpx.Client | None = None):
        s = settings()
        self.base = (base_url or s.gc_api_url).rstrip("/")
        self.athlete = athlete or s.gc_athlete
        self.autoimport_dir = autoimport_dir if autoimport_dir is not None else s.gc_autoimport_dir
        self.http = client or httpx.Client(timeout=5.0)

    def available(self) -> bool:
        try:
            return self.http.get(self.base + "/").status_code == 200
        except httpx.HTTPError:
            return False

    def athletes(self) -> list[str]:
        r = self.http.get(self.base + "/")
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))
        return [row[0].strip() for row in rows[1:] if row] if rows and rows[0] and rows[0][0].lower() == "name" \
            else [line.strip() for line in r.text.splitlines() if line.strip()]

    def export(self, filename: str, data: bytes, start: dt.datetime) -> str | None:
        """Copy the original file to the auto-import folder. Returns the written filename."""
        if not self.autoimport_dir:
            return None
        os.makedirs(self.autoimport_dir, exist_ok=True)
        ext = os.path.splitext(filename)[1].lower() or ".fit"
        name = start.strftime("%Y_%m_%d_%H_%M_%S") + ext
        path = os.path.join(self.autoimport_dir, name)
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(data)
        return name

    def activity_metrics(self, start: dt.datetime) -> dict | None:
        """Find the GC activity starting within ±60 s and return its metric columns as floats."""
        if not self.athlete:
            names = self.athletes()
            if len(names) != 1:
                raise RuntimeError(f"set GC_ATHLETE (found {len(names)} athletes)")
            self.athlete = names[0]
        r = self.http.get(f"{self.base}/{urllib.parse.quote(self.athlete)}")
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            when = _parse_gc_time(row.get("date", ""), row.get("time", ""))
            if when and abs((when - start).total_seconds()) <= 60:
                out = {}
                for k, v in row.items():
                    try:
                        out[k] = float(v)
                    except ValueError:
                        out[k] = v
                return out
        return None


def _parse_gc_time(date_s, time_s):
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(f"{date_s} {time_s}", fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def compare(gc_metrics: dict, ours: dict) -> dict:
    """Side-by-side comparison of overlapping metrics; ours stays authoritative."""
    out = {}
    for gc_name, (mid, conv) in COMPARABLE.items():
        g = gc_metrics.get(gc_name)
        o = ours.get(mid)
        if isinstance(g, float) and o is not None:
            gv = conv(g)
            out[mid] = {"goldencheetah": gv, "athleteiq": o, "abs_diff": o - gv,
                        "pct_diff": ((o - gv) / gv * 100) if gv else None, "gc_column": gc_name}
    return out


def sync(filename: str, data: bytes, start: dt.datetime, ours: dict, gc: GoldenCheetah | None = None) -> dict:
    gc = gc or GoldenCheetah()
    result = {"status": "unavailable", "gc_filename": None, "gc_metrics": {}, "comparison": {}, "message": None,
              "version": VERSION}
    try:
        result["gc_filename"] = gc.export(filename, data, start)
        if result["gc_filename"]:
            result["status"] = "exported"
        if not gc.available():
            result["message"] = (f"GoldenCheetah API not reachable at {gc.base}; "
                                 + ("file placed in auto-import folder" if result["gc_filename"] else "no auto-import folder set"))
            return result
        m = gc.activity_metrics(start)
        if m is None:
            result["message"] = "GoldenCheetah reachable but this activity is not imported there yet"
            return result
        result.update(status="matched", gc_metrics=m, comparison=compare(m, ours), message=None)
    except Exception as e:
        result.update(status="failed", message=f"{type(e).__name__}: {e}")
    return result
