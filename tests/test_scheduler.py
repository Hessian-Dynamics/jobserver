"""
Unit tests for JobScheduler core budget enforcement and queue processing.
"""

import time

from jobserver.core.job import (
    STATUS_COMPLETED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Job,
)
from jobserver.core.registry import HostRegistry
from jobserver.core.scheduler import JobScheduler
from jobserver.core.store import JobStore
from jobserver.transports.local import LocalTransport


def test_scheduler_budget_and_queue(tmp_path):
    store_file = tmp_path / "active_jobs.json"
    store = JobStore(store_file=store_file)
    registry = HostRegistry()
    scheduler = JobScheduler(store=store, registry=registry)
    transport = LocalTransport()

    # Create 3 jobs, each requesting 1 core with a small 0.3s sleep
    jobs = []
    for i in range(3):
        job_dir = tmp_path / f"job_{i}"
        job_dir.mkdir()
        j = Job(
            job_id=f"j_{i}",
            jobname=f"job_{i}",
            driver="python3",
            host="localhost",
            cores=1,
            local_dir=str(job_dir),
            driver_args=["-c", "import time; time.sleep(0.3)"],
        )
        jobs.append(j)

    # Budget is 2 cores on localhost
    max_budget = 2

    # Submit Job 0 -> Should RUN
    j0, is_q0 = scheduler.submit(
        jobs[0], max_budget=max_budget, transport=transport
    )
    assert not is_q0
    assert j0.status == STATUS_RUNNING

    # Submit Job 1 -> Should RUN
    j1, is_q1 = scheduler.submit(
        jobs[1], max_budget=max_budget, transport=transport
    )
    assert not is_q1
    assert j1.status == STATUS_RUNNING

    # Submit Job 2 -> Cores are full (2/2 used)! Should be QUEUED
    j2, is_q2 = scheduler.submit(
        jobs[2], max_budget=max_budget, transport=transport
    )
    assert is_q2
    assert j2.status == STATUS_QUEUED

    # Verify queue count
    queued = scheduler.getQueuedJobs(host="localhost")
    assert len(queued) == 1
    assert queued[0].job_id == "j_2"

    # Wait for running jobs to finish (0.5s)
    time.sleep(0.5)

    # Process queue -> Should promote j2 to RUNNING
    promoted = scheduler.processQueue(
        host="localhost", max_budget=max_budget, transport=transport
    )
    assert len(promoted) == 1
    assert promoted[0].job_id == "j_2"
    assert promoted[0].status == STATUS_RUNNING

    # Wait for promoted job to finish
    time.sleep(0.5)
    scheduler.reapFinishedJobs(host="localhost", transport=transport)
    j2_polled = store.findJob("j_2")
    assert j2_polled.status == STATUS_COMPLETED
