"""Demo athlete: 12 weeks of SYNTHETIC running files, generated and pushed through the real pipeline
(upload → parse → metrics → discoveries). Nothing is hard-coded: whatever discoveries appear are
computed from these files exactly as for a real athlete. The athlete is flagged is_demo."""
from __future__ import annotations

import datetime as dt
import random

from . import models as m
from .synthetic import Seg, Spec, generate, write_fit


def plan(start: dt.datetime, weeks: int = 12, seed: int = 11):
    """Yields (date, Spec) for a progressive 4-runs/week block on a repeated loop."""
    rnd = random.Random(seed)
    out = []
    for w in range(weeks):
        fit = 1.0 + 0.006 * w + rnd.uniform(-0.004, 0.004)  # gradual aerobic improvement
        base = start + dt.timedelta(weeks=w)
        days = [
            (0, "easy", [Seg(2400 + 60 * w, 345, 0.2)]),
            (2, "intervals", [Seg(600, 350)] + sum(([Seg(180, 262 - w * 0.6, 0), Seg(120, 380, 0)] for _ in range(5)), [])
             + [Seg(480, 360)]),
            (4, "tempo", [Seg(600, 345), Seg(1200 + 60 * min(w, 8), 300, 0.3), Seg(480, 355)]),
            (6, "long", [Seg(4200 + 240 * w, 335, 0.5 if w % 3 == 0 else 0.1), Seg(300, 345, 4.0 if w % 3 == 0 else 0)]),
        ]
        for d, kind, segs in days:
            hour = 7 if kind != "tempo" else 18
            temp = 8 + 6 * (w / weeks) + rnd.uniform(-2, 2) + (5 if hour == 18 else 0)
            spec = Spec(start=(base + dt.timedelta(days=d)).replace(hour=hour, minute=rnd.randint(0, 30)),
                        segments=segs, fitness=fit, hr_rest=52, hr_drift_bpm_per_h=6 - 0.25 * w,
                        cadence_spm=168 + 0.3 * w, temperature_c=temp, noise=1.0, seed=rnd.randint(1, 10**6),
                        lat0=51.5, lon0=-0.12)
            out.append((kind, spec))
    return out


def seed(s, weeks: int = 12) -> m.Athlete:
    from .pipeline import submit
    from .worker import enqueue

    ath = m.Athlete(name="Demo Runner (synthetic)", birth_year=1991, rest_hr=52, max_hr=192, lthr=172,
                    goal="aerobic_base", is_demo=True, weight_kg=68)
    s.add(ath)
    s.commit()
    end = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(weeks=weeks)
    jobs = []
    for kind, spec in plan(start, weeks):
        if spec.start > end:
            continue
        recs = generate(spec)
        job, _ = submit(s, ath.id, f"demo_{kind}_{spec.start:%Y%m%d}.fit", write_fit(recs))
        jobs.append(job.id)
    s.commit()
    for j in jobs:  # chronological so each run is compared only with earlier ones
        enqueue(j)
    return ath
