"""
Local process transport runner with POSIX session detachment.
"""

import os
import shutil
import signal
import subprocess
from datetime import datetime
from pathlib import Path

from jobserver.core.job import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_KILLED,
    STATUS_RUNNING,
)
from jobserver.transports.base import BaseTransport


class LocalTransport(BaseTransport):
    """
    Executes and tracks background jobs on the local machine.
    """

    def __init__(self, host_spec=None):
        """
        Initialize LocalTransport.

        :param host_spec: Host configuration dictionary.
        """
        self.host_spec = host_spec or {}

    def submit(self, job):
        """
        Stage files, configure thread caps, and launch detached process.

        :param job: Job instance to launch.
        :return: Updated Job instance with local_pid and RUNNING status.
        """
        local_dir = Path(job.local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        # Stage input files into the job folder
        for inp in job.input_files:
            src_path = Path(inp).resolve()
            if src_path.is_file() and src_path.parent != local_dir:
                dest_path = local_dir / src_path.name
                if not dest_path.exists():
                    shutil.copy2(src_path, dest_path)

        # Prepare log file path
        log_file = local_dir / f"{job.jobname}.log"

        # Environment variables with physical core allocation & affinity
        env = os.environ.copy()
        env["_JOBSERVER_SANDBOX"] = "1"
        if job.cores:
            core_str = str(job.cores)
            env["OMP_NUM_THREADS"] = core_str
            env["OMP_PLACES"] = "cores"
            env["OMP_PROC_BIND"] = "close"
            env["MKL_NUM_THREADS"] = core_str
            env["OPENBLAS_NUM_THREADS"] = core_str

        # Assemble execution command list
        cmd = [job.driver] + job.driver_args

        # Open logfile and spawn detached POSIX process
        with open(log_file, "a", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                cmd,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=str(local_dir),
                env=env,
                start_new_session=True,  # Detach from terminal
                text=True,
            )

        job.local_pid = proc.pid
        job.status = STATUS_RUNNING
        job.save()

        # Save PID token file
        pid_file = local_dir / ".job_pid"
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))

        return job

    def isPidAlive(self, pid):
        """
        Probe process health using waitpid and POSIX signal 0.

        :param pid: Integer process ID.
        :return: Boolean True if process is active.
        """
        if not pid:
            return False

        try:
            # Non-blocking reap if child of current process
            res_pid, _ = os.waitpid(int(pid), os.WNOHANG)
            if res_pid == int(pid):
                return False
        except (ChildProcessError, OSError):
            pass

        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    def poll(self, job):
        """
        Check if local process is still running.

        :param job: Job instance to query.
        :return: Updated Job instance.
        """
        local_dir = Path(job.local_dir)
        pid_file = local_dir / ".job_pid"

        pid = job.local_pid
        if not pid and pid_file.is_file():
            try:
                pid = int(pid_file.read_text().strip())
                job.local_pid = pid
            except Exception:
                pass

        if self.isPidAlive(pid):
            job.status = STATUS_RUNNING
        else:
            # Process exited; inspect output markers
            job.completed_at = datetime.now().isoformat()

            # Check log for errors or normal termination
            log_file = local_dir / f"{job.jobname}.log"
            if log_file.is_file():
                content = log_file.read_text(errors="ignore")
                has_error = (
                    "error" in content.lower()
                    and "normal termination" not in content.lower()
                )
                job.status = STATUS_FAILED if has_error else STATUS_COMPLETED
            else:
                job.status = STATUS_COMPLETED

        job.save()
        return job

    def kill(self, job):
        """
        Terminate local process using SIGTERM.

        :param job: Job instance.
        :return: Boolean True if killed.
        """
        pid = job.local_pid
        if pid and self.isPidAlive(pid):
            try:
                os.kill(int(pid), signal.SIGTERM)
                job.status = STATUS_KILLED
                job.save()
                return True
            except OSError:
                return False
        return False

    def fetchLogs(self, job, tail_lines=50):
        """
        Read trailing lines of the job log file.

        :param job: Job instance.
        :param tail_lines: Number of lines to read.
        :return: String log output.
        """
        local_dir = Path(job.local_dir)
        log_file = local_dir / f"{job.jobname}.log"
        if not log_file.is_file():
            return ""

        with open(log_file, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        return "".join(lines[-tail_lines:])
