"""Dramatiq worker: `dramatiq athleteiq.worker`. In JOB_MODE=inline jobs run in the request thread."""
from __future__ import annotations

import dramatiq

from .config import settings

if settings().job_mode == "queue":
    from dramatiq.brokers.redis import RedisBroker
    dramatiq.set_broker(RedisBroker(url=settings().redis_url))
else:
    from dramatiq.brokers.stub import StubBroker
    dramatiq.set_broker(StubBroker())


@dramatiq.actor(max_retries=2, min_backoff=5_000, time_limit=15 * 60 * 1000, queue_name="analysis")
def analyse(job_id: str):
    from .pipeline import run_job
    run_job(job_id)


def enqueue(job_id) -> None:
    if settings().job_mode == "queue":
        analyse.send(str(job_id))
    else:
        from .pipeline import run_job
        run_job(str(job_id))
