"""
JobServer: Compute orchestration and job control infrastructure.
"""

from jobserver.core.dispatcher import JobDispatcher
from jobserver.core.job import Job
from jobserver.core.jobcontrol import (
    FLAG_HOST,
    FLAG_INPUT,
    FLAG_JOBNAME,
    FLAG_SCRATCH,
    FLAG_SUBHOST,
    extractJobControlArgs,
    parseHostSpec,
    resolveJobName,
)
from jobserver.core.registry import HostRegistry
from jobserver.core.store import JobStore


__version__ = "0.1.0"
__all__ = [
    "Job",
    "JobDispatcher",
    "JobStore",
    "HostRegistry",
    "extractJobControlArgs",
    "parseHostSpec",
    "resolveJobName",
    "FLAG_JOBNAME",
    "FLAG_HOST",
    "FLAG_SUBHOST",
    "FLAG_SCRATCH",
    "FLAG_INPUT",
]
