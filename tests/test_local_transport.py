"""
Unit tests for LocalTransport background execution and polling.
"""

import time

from jobserver.core.job import STATUS_COMPLETED, STATUS_RUNNING, Job
from jobserver.transports.local import LocalTransport


def test_local_transport_submit_and_poll(tmp_path):
    job_dir = tmp_path / "test_calc"
    job_dir.mkdir()

    # Create dummy input file
    input_file = tmp_path / "input.xyz"
    input_file.write_text("dummy coords")

    job = Job(
        job_id="test_local_001",
        jobname="test_calc",
        driver="python3",
        host="localhost",
        cores=2,
        local_dir=str(job_dir),
        input_files=[str(input_file)],
        driver_args=[
            "-c",
            "import time; print('Starting'); time.sleep(0.3); print('Done')",
        ],
    )

    transport = LocalTransport()

    # 1. Submit (asynchronous launch)
    submitted_job = transport.submit(job)
    assert submitted_job.status == STATUS_RUNNING
    assert submitted_job.local_pid is not None
    assert (job_dir / "input.xyz").exists()
    assert (job_dir / ".job_pid").exists()

    # 2. Poll while running
    assert transport.isPidAlive(submitted_job.local_pid)

    # 3. Wait for sleep to finish and poll completion
    time.sleep(0.6)
    polled_job = transport.poll(submitted_job)
    assert polled_job.status == STATUS_COMPLETED
    assert not transport.isPidAlive(submitted_job.local_pid)

    # 4. Check logs
    logs = transport.fetchLogs(polled_job)
    assert "Starting" in logs
    assert "Done" in logs
