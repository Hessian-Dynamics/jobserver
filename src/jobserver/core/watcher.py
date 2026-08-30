"""
JobWatcher: Self-terminating background queue monitoring daemon.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from jobserver.core.job import (
    STATUS_QUEUED,
    STATUS_RUNNING,
)
from jobserver.core.registry import HostRegistry
from jobserver.core.scheduler import JobScheduler
from jobserver.core.store import JobStore
from jobserver.transports.local import LocalTransport
from jobserver.transports.ssh import SSHTransport


DAEMON_PID_FILE = Path.home() / ".jobserver" / ".daemon_pid"


class JobWatcher:
    """
    Autonomous queue watcher that drains queues and exits when all jobs finish.
    """

    def __init__(self, scheduler=None, store=None, registry=None):
        """
        Initialize JobWatcher.

        :param scheduler: Optional custom JobScheduler instance.
        :param store: Optional custom JobStore instance.
        :param registry: Optional custom HostRegistry instance.
        """
        self.store = store or JobStore()
        self.registry = registry or HostRegistry()
        self.scheduler = scheduler or JobScheduler(
            store=self.store, registry=self.registry
        )

    def getTransport(self, host_name):
        """
        Resolve and instantiate transport for the specified host.

        :param host_name: Target host name string.
        :return: BaseTransport instance.
        """
        spec = self.registry.getHost(host_name)
        host_type = spec.get("type", "local").lower()
        if host_type == "ssh":
            return SSHTransport(host_spec=spec)
        return LocalTransport(host_spec=spec)

    def hasActiveJobs(self):
        """
        Check if any calculations are currently RUNNING or QUEUED.

        :return: Boolean True if active jobs remain in the store.
        """
        jobs = self.store.listJobs()
        return any(j.status in (STATUS_RUNNING, STATUS_QUEUED) for j in jobs)

    def runLoop(self, interval_seconds=3, max_idle_cycles=3):
        """
        Run monitoring loop until all running and queued jobs complete.

        :param interval_seconds: Sleep interval between queue drain cycles.
        :param max_idle_cycles: Consecutive empty cycles before exiting.
        """
        idle_count = 0

        while True:
            active_jobs = self.store.listJobs()
            hosts = {
                j.host
                for j in active_jobs
                if j.status in (STATUS_RUNNING, STATUS_QUEUED)
            }

            for host in hosts:
                try:
                    transport = self.getTransport(host)
                    self.scheduler.processQueue(host=host, transport=transport)
                except Exception:
                    pass

            if not self.hasActiveJobs():
                idle_count += 1
                if idle_count >= max_idle_cycles:
                    break
            else:
                idle_count = 0

            time.sleep(interval_seconds)

        # Cleanup daemon pid file upon clean termination
        if DAEMON_PID_FILE.is_file():
            try:
                DAEMON_PID_FILE.unlink()
            except OSError:
                pass

    @classmethod
    def isDaemonRunning(cls):
        """
        Check if a background watcher daemon is already active.

        :return: Boolean True if daemon process is alive.
        """
        if not DAEMON_PID_FILE.is_file():
            return False

        try:
            pid = int(DAEMON_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    @classmethod
    def spawnDaemon(cls, interval_seconds=3):
        """
        Spawn detached background daemon if one is not already running.
        """
        if cls.isDaemonRunning():
            return

        DAEMON_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_file = DAEMON_PID_FILE.parent / "daemon.log"

        cmd = [
            sys.executable,
            "-m",
            "jobserver.cli",
            "daemon",
            "--interval",
            str(interval_seconds),
        ]

        with open(log_file, "a", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                cmd,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        DAEMON_PID_FILE.write_text(str(proc.pid))
