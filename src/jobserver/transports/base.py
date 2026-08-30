"""
Abstract base class defining transport execution interface.
"""

from abc import ABC, abstractmethod


class BaseTransport(ABC):
    """
    Abstract transport interface for local and remote job execution.
    """

    @abstractmethod
    def submit(self, job):
        """
        Stage files and launch the job asynchronously.

        :param job: Job instance to submit.
        :return: Updated Job instance with PID and SUBMITTED/RUNNING status.
        """
        pass

    @abstractmethod
    def poll(self, job):
        """
        Check job execution status and fetch artifacts if complete.

        :param job: Job instance to query.
        :return: Updated Job instance.
        """
        pass

    @abstractmethod
    def kill(self, job):
        """
        Terminate running calculation process.

        :param job: Job instance to terminate.
        :return: Boolean True if termination succeeded.
        """
        pass

    @abstractmethod
    def fetchLogs(self, job, tail_lines=50):
        """
        Retrieve latest output log lines.

        :param job: Job instance.
        :param tail_lines: Number of trailing lines to return.
        :return: String containing latest log lines.
        """
        pass
