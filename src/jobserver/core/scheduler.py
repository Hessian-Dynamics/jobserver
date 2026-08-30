"""
JobScheduler: Manages hardware core budgets, waiting queues, and job promotions.
"""

from jobserver.core.job import (
    STATUS_QUEUED,
    STATUS_RUNNING,
)
from jobserver.core.registry import HostRegistry
from jobserver.core.store import JobStore


class JobScheduler:
    """
    Manages core budgets, enqueues overflow jobs, and processes waiting queues.
    """

    def __init__(self, store=None, registry=None):
        """
        Initialize JobScheduler instance.

        :param store: Optional custom JobStore instance.
        :param registry: Optional custom HostRegistry instance.
        """
        self.store = store or JobStore()
        self.registry = registry or HostRegistry()

    def getRunningJobs(self, host=None):
        """
        Retrieve list of currently RUNNING jobs for a host.

        :param host: Optional string host name filter.
        :return: List of Job instances in RUNNING state.
        """
        all_jobs = self.store.listJobs()
        return [
            j
            for j in all_jobs
            if j.status == STATUS_RUNNING and (host is None or j.host == host)
        ]

    def getQueuedJobs(self, host=None):
        """
        Retrieve list of QUEUED jobs in strict FIFO order (oldest first).

        :param host: Optional string host name filter.
        :return: Sorted list of Job instances in QUEUED state.
        """
        all_jobs = self.store.listJobs()
        queued = [
            j
            for j in all_jobs
            if j.status == STATUS_QUEUED and (host is None or j.host == host)
        ]
        queued.sort(key=lambda j: j.submitted_at or "")
        return queued

    def getUsedCores(self, host="localhost"):
        """
        Calculate sum of physical cores occupied by running jobs on host.

        :param host: Target host name string.
        :return: Integer count of active cores currently in use.
        """
        running = self.getRunningJobs(host=host)
        return sum(j.cores or 1 for j in running)

    def reapFinishedJobs(self, host, transport=None):
        """
        Poll all active calculations to update status of completed runs.

        :param host: Target host name string.
        :param transport: BaseTransport instance used for polling.
        """
        if transport is None:
            return

        for job in self.getRunningJobs(host=host):
            transport.poll(job)

    def getAvailableCores(self, host="localhost", max_budget=None):
        """
        Calculate free physical cores available for new calculations.

        :param host: Target host name string.
        :param max_budget: Optional explicit core budget cap requested by user.
        :return: Integer count of unallocated free cores.
        """
        if max_budget is None:
            spec = self.registry.getHost(host)
            max_budget = spec.get("max_cores", 1)

        used = self.getUsedCores(host=host)
        return max(0, max_budget - used)

    def submit(self, job, max_budget, transport):
        """
        Submit a new calculation or hold in queue if core budget is full.

        :param job: Job instance to submit.
        :param max_budget: Total allowed core budget for the host.
        :param transport: BaseTransport instance for executing the process.
        :return: Tuple of (submitted_or_queued_job, is_queued_boolean).
        """
        # 1. Poll running jobs first to refresh ground-truth hardware state
        self.reapFinishedJobs(job.host, transport=transport)

        # 2. Check available core capacity against requested budget
        available = self.getAvailableCores(job.host, max_budget=max_budget)
        needed = job.cores or 1

        if available >= needed:
            # Budget available: launch immediately
            submitted = transport.submit(job)
            self.store.register(submitted)
            return submitted, False
        else:
            # Budget full: persist as QUEUED in store
            job.status = STATUS_QUEUED
            job.save()
            self.store.register(job)
            return job, True

    def processQueue(self, host="localhost", max_budget=None, transport=None):
        """
        Drain the waiting queue and promote jobs that fit in freed cores.

        :param host: Target host name string.
        :param max_budget: Total allowed core budget for the host.
        :param transport: BaseTransport instance for launching promoted jobs.
        :return: List of newly promoted Job instances now in RUNNING state.
        """
        if transport is None:
            return []

        # 1. Update ground-truth state by polling active jobs
        self.reapFinishedJobs(host, transport=transport)

        promoted = []
        for q_job in self.getQueuedJobs(host=host):
            available = self.getAvailableCores(host=host, max_budget=max_budget)
            needed = q_job.cores or 1

            if available >= needed:
                running_job = transport.submit(q_job)
                self.store.register(running_job)
                promoted.append(running_job)
            else:
                # Not enough cores for this queued job; wait for next cycle
                break

        return promoted
