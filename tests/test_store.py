"""
Unit tests for JobStore registration and metadata persistence.
"""

from jobserver.core.job import STATUS_PENDING, Job
from jobserver.core.store import JobStore


def test_job_store_lifecycle(tmp_path):
    store_file = tmp_path / "active_jobs.json"
    store = JobStore(store_file=store_file)

    job_dir = tmp_path / "ethanol_run"
    job_dir.mkdir()

    job = Job(
        job_id="eth_123",
        jobname="ethanol_run",
        driver="hilbert-xtbmd",
        host="localhost",
        local_dir=str(job_dir),
        status=STATUS_PENDING,
    )
    job.save()

    # Register in store
    store.register(job)
    assert "eth_123" in store.active_jobs

    # Find job by ID and by Name
    found_by_id = store.findJob("eth_123")
    assert found_by_id.job_id == "eth_123"
    assert found_by_id.jobname == "ethanol_run"

    found_by_name = store.findJob("ethanol_run")
    assert found_by_name.job_id == "eth_123"

    # List jobs
    all_jobs = store.listJobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].job_id == "eth_123"

    # Unregister
    store.unregister("eth_123")
    assert "eth_123" not in store.active_jobs
