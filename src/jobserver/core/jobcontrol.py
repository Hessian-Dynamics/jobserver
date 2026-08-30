"""
Job control flag definitions and argument separation utilities.
"""

from datetime import datetime
from pathlib import Path


# Flag constants
FLAG_JOBNAME = "-JOBNAME"
FLAG_HOST = "-HOST"
FLAG_SUBHOST = "-SUBHOST"
FLAG_SCRATCH = "-scratch"
FLAG_INPUT = "-i"

# Default constants
DEFAULT_HOST = "localhost"
DEFAULT_SUBHOST = "localhost"
DEFAULT_JOB_PREFIX = "job"


def parseHostSpec(host_str):
    """
    Parse a host specification string into hostname and thread count.

    Examples:
        'localhost:10' -> ('localhost', 10)
        'cluster01:32' -> ('cluster01', 32)
        'node01'       -> ('node01', None)
        None           -> ('localhost', None)

    :param host_str: Raw host string (e.g. 'localhost:10').
    :return: Tuple of (host_name, num_threads).
    """
    if not host_str:
        return DEFAULT_HOST, None

    raw_str = str(host_str).strip()
    if ":" in raw_str:
        parts = raw_str.split(":", 1)
        host_name = parts[0].strip() or DEFAULT_HOST
        try:
            num_threads = int(parts[1].strip())
        except ValueError:
            num_threads = None
        return host_name, num_threads

    return raw_str, None


def resolveJobName(jobname=None, input_file=None):
    """
    Resolve job name from explicit flag, input file stem, or timestamp.

    :param jobname: Explicit job name provided via -JOBNAME.
    :param input_file: Path to primary input coordinate file.
    :return: Resolved string job name.
    """
    if jobname and str(jobname).strip():
        return str(jobname).strip()

    if input_file:
        stem = Path(input_file).stem
        if stem:
            return stem

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{DEFAULT_JOB_PREFIX}_{timestamp}"


def extractJobControlArgs(args_list):
    """
    Separate job control flags from driver arguments.

    :param args_list: Full CLI argument list (e.g. sys.argv[1:]).
    :return: Tuple of (job_control_dict, remaining_driver_args).
    """
    if args_list is None:
        args_list = []

    control = {
        "jobname": None,
        "host": DEFAULT_HOST,
        "subhost": DEFAULT_SUBHOST,
        "scratch": None,
        "input": None,
    }

    driver_args = []
    i = 0
    while i < len(args_list):
        arg = args_list[i]

        if arg == FLAG_JOBNAME and i + 1 < len(args_list):
            control["jobname"] = args_list[i + 1]
            i += 2
        elif arg == FLAG_HOST and i + 1 < len(args_list):
            control["host"] = args_list[i + 1]
            i += 2
        elif arg == FLAG_SUBHOST and i + 1 < len(args_list):
            control["subhost"] = args_list[i + 1]
            i += 2
        elif arg == FLAG_SCRATCH and i + 1 < len(args_list):
            control["scratch"] = args_list[i + 1]
            i += 2
        elif arg == FLAG_INPUT and i + 1 < len(args_list):
            control["input"] = args_list[i + 1]
            driver_args.extend([arg, args_list[i + 1]])
            i += 2
        else:
            driver_args.append(arg)
            i += 1

    # Resolve jobname if not explicitly set
    control["jobname"] = resolveJobName(
        jobname=control["jobname"], input_file=control["input"]
    )

    return control, driver_args
