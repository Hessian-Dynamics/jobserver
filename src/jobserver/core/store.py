"""
Active job registry store and atomic metadata persistence.
"""

import json
from pathlib import Path

from jobserver.core.job import JOB_INFO_FILENAME, Job


DEFAULT_STORE_DIR = Path.home() / ".jobserver"
DEFAULT_STORE_FILE = DEFAULT_STORE_DIR / "active_jobs.json"


class JobStore:
    """
    Manages the global index of active and recent jobs.
    """

    def __init__(self, store_file=None):
        """
        Initialize JobStore instance.

        :param store_file: Path to active_jobs.json registry file.
        """
        self.store_file = (
            Path(store_file).resolve() if store_file else DEFAULT_STORE_FILE
        )
        self.store_dir = self.store_file.parent
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.active_jobs = {}
        self.load()

    def load(self):
        """
        Load active jobs index from disk.
        """
        if self.store_file.is_file():
            try:
                with open(self.store_file, encoding="utf-8") as f:
                    self.active_jobs = json.load(f)
            except Exception:
                self.active_jobs = {}
        else:
            self.active_jobs = {}

    def save(self):
        """
        Save active jobs index to disk atomically.
        """
        tmp_file = self.store_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.active_jobs, f, indent=2)
        tmp_file.replace(self.store_file)

    def register(self, job):
        """
        Register a new or running job into the index.

        :param job: Job instance.
        """
        self.active_jobs[job.job_id] = {
            "jobname": job.jobname,
            "local_dir": str(job.local_dir),
            "host": job.host,
            "submitted_at": job.submitted_at,
        }
        self.save()

    def unregister(self, job_id):
        """
        Remove a job from the active index.

        :param job_id: Unique string identifier of job.
        """
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
            self.save()

    def findJob(self, job_identifier):
        """
        Locate and load a Job instance by job_id or jobname.

        :param job_identifier: Unique job_id or human-readable jobname.
        :return: Loaded Job instance.
        """
        # 1. Exact match on job_id
        if job_identifier in self.active_jobs:
            entry = self.active_jobs[job_identifier]
            job_file = Path(entry["local_dir"]) / JOB_INFO_FILENAME
            if job_file.is_file():
                return Job.load(job_file)

        # 2. Match on jobname
        for _j_id, entry in self.active_jobs.items():
            if entry.get("jobname") == job_identifier:
                job_file = Path(entry["local_dir"]) / JOB_INFO_FILENAME
                if job_file.is_file():
                    return Job.load(job_file)

        # 3. Check current directory for .job_info.json
        local_job_file = Path.cwd() / JOB_INFO_FILENAME
        if local_job_file.is_file():
            job = Job.load(local_job_file)
            if job.job_id == job_identifier or job.jobname == job_identifier:
                return job

        # 4. Check subfolder in current directory
        sub_job_file = Path.cwd() / job_identifier / JOB_INFO_FILENAME
        if sub_job_file.is_file():
            return Job.load(sub_job_file)

        raise FileNotFoundError(
            f"Could not find calculation matching '{job_identifier}'."
        )

    def listJobs(self):
        """
        Load and return all registered Job instances.

        :return: List of Job instances.
        """
        jobs = []
        dead_ids = []

        for j_id, entry in self.active_jobs.items():
            job_file = Path(entry["local_dir"]) / JOB_INFO_FILENAME
            if job_file.is_file():
                try:
                    jobs.append(Job.load(job_file))
                except Exception:
                    pass
            else:
                dead_ids.append(j_id)

        # Clean up entries whose folders were deleted by user
        if dead_ids:
            for d_id in dead_ids:
                del self.active_jobs[d_id]
            self.save()

        return jobs
