"""
Remote SSH and Rsync process transport runner for distributed compute hosts.
"""

import os
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


class SSHTransport(BaseTransport):
    """
    Executes and tracks asynchronous jobs on remote SSH hosts using rsync.
    """

    def __init__(self, host_spec=None):
        """
        Initialize SSHTransport with host specification.

        :param host_spec: Host configuration dictionary from hosts.toml.
        """
        self.host_spec = host_spec or {}
        self.hostname = self.host_spec.get("hostname", "localhost")
        default_user = os.getenv("USER", "root")
        self.username = self.host_spec.get("username", default_user)
        self.port = str(self.host_spec.get("port", 22))
        self.key_filename = self.host_spec.get("key_filename")
        self.remote_scratch = self.host_spec.get(
            "remote_scratch", f"/tmp/jobserver_{self.username}"
        )
        self.hilbert_env_bin = self.host_spec.get("hilbert_env_bin", "")

    def getSSHBaseCmd(self):
        """
        Build base SSH command list with port and key options.

        :return: List of SSH command arguments.
        """
        cmd = ["ssh", "-p", self.port]
        if self.key_filename:
            expanded_key = str(Path(self.key_filename).expanduser())
            cmd.extend(["-i", expanded_key])
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.append(f"{self.username}@{self.hostname}")
        return cmd

    def getRsyncSSHString(self):
        """
        Build SSH string for rsync -e argument.

        :return: String for rsync -e flag.
        """
        parts = ["ssh", "-p", self.port, "-o", "StrictHostKeyChecking=no"]
        if self.key_filename:
            expanded_key = str(Path(self.key_filename).expanduser())
            parts.extend(["-i", expanded_key])
        return " ".join(parts)

    def runSSHCommand(self, remote_command):
        """
        Execute command on remote host via SSH.

        :param remote_command: Shell string to run on remote host.
        :return: subprocess.CompletedProcess object.
        """
        cmd = self.getSSHBaseCmd() + [remote_command]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

    def submit(self, job):
        """
        Stage files, create remote scratch, and launch detached remote process.

        :param job: Job instance to launch.
        :return: Updated Job instance with remote_pid and RUNNING status.
        """
        remote_job_dir = f"{self.remote_scratch}/{job.jobname}"
        job.remote_dir = remote_job_dir

        # 1. Create remote scratch directory
        self.runSSHCommand(f"mkdir -p {remote_job_dir}")

        # 2. Rsync input files to remote host
        rsync_ssh = self.getRsyncSSHString()
        for inp in job.input_files:
            src_path = Path(inp).resolve()
            if src_path.is_file():
                dest = f"{self.username}@{self.hostname}:{remote_job_dir}/"
                rsync_cmd = [
                    "rsync",
                    "-avz",
                    "-e",
                    rsync_ssh,
                    str(src_path),
                    dest,
                ]
                subprocess.run(rsync_cmd, capture_output=True, check=False)

        # 3. Resolve executable path on remote host
        driver_cmd = job.driver
        if self.hilbert_env_bin:
            driver_cmd = f"{self.hilbert_env_bin.rstrip('/')}/{job.driver}"

        args_str = " ".join(job.driver_args)
        log_file = f"{job.jobname}.log"

        # 4. Launch remote background process with nohup & capture PID
        remote_script = (
            f"cd {remote_job_dir} && "
            f"nohup {driver_cmd} {args_str} > {log_file} 2>&1 & "
            f"echo $! > .job_pid && cat .job_pid"
        )

        res = self.runSSHCommand(remote_script)
        remote_pid = res.stdout.strip()
        if remote_pid.isdigit():
            job.remote_pid = int(remote_pid)
            job.status = STATUS_RUNNING
        else:
            job.status = STATUS_FAILED

        job.save()
        return job

    def isRemotePidAlive(self, pid):
        """
        Check if remote process is alive using kill -0 on remote host.

        :param pid: Integer process ID.
        :return: Boolean True if remote process is alive.
        """
        if not pid:
            return False
        res = self.runSSHCommand(f"kill -0 {pid}")
        return res.returncode == 0

    def syncArtifacts(self, job):
        """
        Rsync all output files from remote scratch back to local job directory.

        :param job: Job instance.
        """
        local_dir = Path(job.local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        remote_src = f"{self.username}@{self.hostname}:{job.remote_dir}/"
        rsync_ssh = self.getRsyncSSHString()

        rsync_cmd = [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh,
            remote_src,
            str(local_dir),
        ]
        subprocess.run(rsync_cmd, capture_output=True, check=False)

    def poll(self, job):
        """
        Check remote process status and download artifacts if complete.

        :param job: Job instance.
        :return: Updated Job instance.
        """
        if not job.remote_pid:
            res = self.runSSHCommand(f"cat {job.remote_dir}/.job_pid")
            if res.returncode == 0 and res.stdout.strip().isdigit():
                job.remote_pid = int(res.stdout.strip())

        if self.isRemotePidAlive(job.remote_pid):
            job.status = STATUS_RUNNING
        else:
            # Remote calculation finished! Auto-download results
            job.completed_at = datetime.now().isoformat()
            self.syncArtifacts(job)

            local_log = Path(job.local_dir) / f"{job.jobname}.log"
            if local_log.is_file():
                content = local_log.read_text(errors="ignore")
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
        Terminate remote process via SSH.

        :param job: Job instance.
        :return: Boolean True if killed.
        """
        if job.remote_pid and self.isRemotePidAlive(job.remote_pid):
            res = self.runSSHCommand(f"kill -15 {job.remote_pid}")
            if res.returncode == 0:
                job.status = STATUS_KILLED
                job.save()
                return True
        return False

    def fetchLogs(self, job, tail_lines=50):
        """
        Stream trailing lines of remote log file.

        :param job: Job instance.
        :param tail_lines: Number of lines to read.
        :return: String log output.
        """
        remote_log = f"{job.remote_dir}/{job.jobname}.log"
        res = self.runSSHCommand(f"tail -n {tail_lines} {remote_log}")
        return res.stdout if res.returncode == 0 else ""
