"""
Job data model and status state management.
"""

import json
from datetime import datetime
from pathlib import Path


# Status constants
STATUS_PENDING = "PENDING"
STATUS_QUEUED = "QUEUED"
STATUS_SUBMITTED = "SUBMITTED"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_KILLED = "KILLED"

JOB_INFO_FILENAME = ".job_info.json"


class Job:
    """
    Encapsulates calculation metadata, execution state, and lifecycle tracking.
    """

    def __init__(
        self,
        job_id,
        jobname,
        driver,
        host="localhost",
        cores=None,
        threads=None,
        subhost=None,
        local_dir=None,
        remote_dir=None,
        remote_pid=None,
        local_pid=None,
        status=STATUS_PENDING,
        submitted_at=None,
        completed_at=None,
        input_files=None,
        driver_args=None,
    ):
        """
        Initialize Job instance.

        :param job_id: Unique string identifier for the job.
        :param jobname: Human-readable job and folder name.
        :param driver: Executable or driver name (e.g. 'hilbert-xtbmd').
        :param host: Execution host name (e.g. 'localhost', 'cluster01').
        :param cores: Allocated physical CPU cores.
        :param threads: Legacy alias for cores.
        :param subhost: Optional sub-worker host.
        :param local_dir: Local sandboxed working directory.
        :param remote_dir: Remote working scratch directory.
        :param remote_pid: Remote background process ID.
        :param local_pid: Local background process ID.
        :param status: Current lifecycle status.
        :param submitted_at: Submission ISO timestamp.
        :param completed_at: Completion ISO timestamp.
        :param input_files: List of input filenames.
        :param driver_args: Command line arguments passed to the driver.
        """
        self.job_id = job_id
        self.jobname = jobname
        self.driver = driver
        self.host = host
        self.cores = cores if cores is not None else threads
        self.threads = self.cores  # backward compatibility alias
        self.subhost = subhost
        self.local_dir = (
            str(Path(local_dir).resolve()) if local_dir else str(Path.cwd())
        )
        self.remote_dir = remote_dir
        self.remote_pid = remote_pid
        self.local_pid = local_pid
        self.status = status
        self.submitted_at = submitted_at or datetime.now().isoformat()
        self.completed_at = completed_at
        self.input_files = input_files or []
        self.driver_args = driver_args or []

    def toDict(self):
        """
        Serialize Job instance to dictionary.

        :return: JSON-serializable dictionary.
        """
        return {
            "job_id": self.job_id,
            "jobname": self.jobname,
            "driver": self.driver,
            "host": self.host,
            "cores": self.cores,
            "threads": self.threads,
            "subhost": self.subhost,
            "local_dir": self.local_dir,
            "remote_dir": self.remote_dir,
            "remote_pid": self.remote_pid,
            "local_pid": self.local_pid,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "completed_at": self.completed_at,
            "input_files": self.input_files,
            "driver_args": self.driver_args,
        }

    def save(self, filepath=None):
        """
        Save job metadata to .job_info.json atomically.

        :param filepath: Target file path (default: local_dir/.job_info.json).
        :return: Path to saved file.
        """
        target = (
            Path(filepath)
            if filepath
            else Path(self.local_dir) / JOB_INFO_FILENAME
        )
        tmp_target = target.with_suffix(".tmp")

        data = self.toDict()
        with open(tmp_target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        tmp_target.replace(target)
        return target

    @classmethod
    def fromDict(cls, data):
        """
        Construct Job instance from dictionary.

        :param data: Dictionary containing job fields.
        :return: Job instance.
        """
        return cls(
            job_id=data.get("job_id"),
            jobname=data.get("jobname"),
            driver=data.get("driver"),
            host=data.get("host", "localhost"),
            cores=data.get("cores"),
            threads=data.get("threads"),
            subhost=data.get("subhost"),
            local_dir=data.get("local_dir"),
            remote_dir=data.get("remote_dir"),
            remote_pid=data.get("remote_pid"),
            local_pid=data.get("local_pid"),
            status=data.get("status", STATUS_PENDING),
            submitted_at=data.get("submitted_at"),
            completed_at=data.get("completed_at"),
            input_files=data.get("input_files"),
            driver_args=data.get("driver_args"),
        )

    @classmethod
    def load(cls, filepath):
        """
        Load Job instance from metadata JSON file.

        :param filepath: Path to .job_info.json file.
        :return: Job instance.
        """
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Job metadata file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls.fromDict(data)
