"""
Master job dispatcher connecting CLI arguments, host resolution, and transports.
"""

from datetime import datetime
from pathlib import Path

from jobserver.core.job import Job
from jobserver.core.jobcontrol import extractJobControlArgs, parseHostSpec
from jobserver.core.registry import HostRegistry
from jobserver.core.scheduler import JobScheduler
from jobserver.core.store import JobStore
from jobserver.core.watcher import JobWatcher
from jobserver.transports.local import LocalTransport
from jobserver.transports.ssh import SSHTransport


class JobDispatcher:
    """
    Orchestrates job parsing, host selection, and async transport submission.
    """

    def __init__(self, config_path=None):
        """
        Initialize JobDispatcher with registry, store, and scheduler.

        :param config_path: Optional path to hosts.toml.
        """
        self.registry = HostRegistry(config_path=config_path)
        self.store = JobStore()
        self.scheduler = JobScheduler(store=self.store, registry=self.registry)

    def getTransport(self, host_spec):
        """
        Instantiate the appropriate transport based on host type.

        :param host_spec: Host configuration dictionary.
        :return: BaseTransport instance (LocalTransport or SSHTransport).
        """
        host_type = host_spec.get("type", "local").lower()
        if host_type == "ssh":
            return SSHTransport(host_spec=host_spec)
        return LocalTransport(host_spec=host_spec)

    def launch(self, driver_name, raw_args=None):
        """
        Parse arguments, stage job directory, and submit calculation.

        :param driver_name: Name of executable (e.g. 'hilbert-xtbmd').
        :param raw_args: List of command-line arguments.
        :return: Submitted Job instance.
        """
        # 1. Separate job control flags from driver arguments
        control, driver_args = extractJobControlArgs(raw_args)
        jobname = control["jobname"]
        host_str = control["host"]
        subhost_str = control["subhost"]
        input_file = control["input"]

        # 2. Parse and validate host specification
        host_name, requested_cores = parseHostSpec(host_str)
        host_spec, effective_cores = self.registry.validateHost(
            host_name, requested_cores=requested_cores
        )

        # 3. Create unique Job ID & local directory sandbox
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"{jobname}_{timestamp}"
        local_dir = Path.cwd() / jobname
        local_dir.mkdir(parents=True, exist_ok=True)

        input_files = [input_file] if input_file else []

        # Transform -i path to local basename inside the sandbox directory
        sandboxed_args = []
        i = 0
        while i < len(driver_args):
            arg = driver_args[i]
            if arg == "-i" and i + 1 < len(driver_args):
                sandboxed_args.extend(["-i", Path(driver_args[i + 1]).name])
                i += 2
            else:
                sandboxed_args.append(arg)
                i += 1

        if "-JOBNAME" not in sandboxed_args:
            sandboxed_args.extend(["-JOBNAME", jobname])

        # 4. Instantiate Job model
        job = Job(
            job_id=job_id,
            jobname=jobname,
            driver=driver_name,
            host=host_name,
            cores=effective_cores,
            subhost=subhost_str,
            local_dir=str(local_dir),
            input_files=input_files,
            driver_args=sandboxed_args,
        )

        # 5. Submit through scheduler enforcing core budget
        transport = self.getTransport(host_spec)
        submitted_job, is_queued = self.scheduler.submit(
            job, max_budget=effective_cores, transport=transport
        )

        # 6. If queued, ensure background watcher daemon is running
        if is_queued:
            JobWatcher.spawnDaemon()

        # 7. Print user-facing confirmation
        if is_queued:
            status_desc = "QUEUED (Waiting for available physical cores)"
        else:
            pid = (
                submitted_job.local_pid
                if host_spec.get("type") == "local"
                else submitted_job.remote_pid
            )
            status_desc = f"RUNNING (PID: {pid})"

        print("\n" + "=" * 60)
        print(f" [SUCCESS] Job '{jobname}' submitted to '{host_name}'.")
        print("=" * 60)
        print(f" Job ID     : {job.job_id}")
        print(f" Status     : {status_desc}")
        print(f" Cores      : {effective_cores} Physical Cores (Pinned)")
        print(f" Sandbox    : {local_dir}")
        print(f" To Check   : jobserver poll {jobname}")
        print("=" * 60 + "\n")

        return submitted_job
