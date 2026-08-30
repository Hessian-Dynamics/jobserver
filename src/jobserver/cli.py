"""
Command-line interface for querying, polling, and managing JobServer runs.
"""

import argparse
import sys

from jobserver.core.dispatcher import JobDispatcher
from jobserver.core.job import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_KILLED,
    STATUS_QUEUED,
    STATUS_RUNNING,
)
from jobserver.core.store import JobStore
from jobserver.core.watcher import JobWatcher


def cmd_list(args, store, dispatcher):
    """
    List all active and recent jobs in a formatted table.

    :param args: Parsed argparse namespace.
    :param store: JobStore instance.
    :param dispatcher: JobDispatcher instance.
    :return: Integer exit code.
    """
    # Drain queues across active hosts before rendering table
    active_jobs = store.listJobs()
    hosts = {
        j.host
        for j in active_jobs
        if j.status in (STATUS_RUNNING, STATUS_QUEUED)
    }
    for h in hosts:
        try:
            spec = dispatcher.registry.getHost(h)
            trans = dispatcher.getTransport(spec)
            dispatcher.scheduler.processQueue(host=h, transport=trans)
        except Exception:
            pass

    jobs = store.listJobs()
    if not jobs:
        print("\nNo active calculations found.\n")
        return 0

    print("\n" + "=" * 80)
    print(
        f"{'JOB ID':<26} {'NAME':<14} {'HOST':<10} "
        f"{'CORES':<7} {'STATUS':<11} {'PID':<6}"
    )
    print("=" * 80)

    for j in jobs:
        pid = str(j.remote_pid if j.remote_pid else j.local_pid or "-")
        cores_str = str(j.cores or "-")
        print(
            f"{j.job_id:<26} {j.jobname:<14} {j.host:<10} "
            f"{cores_str:<7} {j.status:<11} {pid:<6}"
        )

    print("=" * 80 + "\n")
    return 0


def cmd_poll(args, store, dispatcher):
    """
    Poll the status of a specific job and auto-fetch artifacts if finished.

    :param args: Parsed argparse namespace.
    :param store: JobStore instance.
    :param dispatcher: JobDispatcher instance.
    :return: Integer exit code.
    """
    target = args.job_id
    if not target:
        target = "."

    try:
        job = store.findJob(target)
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}\n")
        return 1

    host_spec = dispatcher.registry.getHost(job.host)
    transport = dispatcher.getTransport(host_spec)

    print(
        f"\nPolling job '{job.jobname}' (ID: {job.job_id}) on '{job.host}'..."
    )
    # Drain queue and poll this specific job
    dispatcher.scheduler.processQueue(host=job.host, transport=transport)
    updated_job = transport.poll(job)

    print("\n" + "-" * 60)
    print(f" Job Name  : {updated_job.jobname}")
    print(f" Job ID    : {updated_job.job_id}")
    print(f" Host      : {updated_job.host}")
    print(f" Cores     : {updated_job.cores or '-'} (Physical Cores Pinned)")
    print(f" Status    : {updated_job.status}")
    print(f" Directory : {updated_job.local_dir}")
    print("-" * 60)

    if updated_job.status == STATUS_RUNNING:
        print("\nLatest log output:")
        print(transport.fetchLogs(updated_job, tail_lines=15))
        print(
            f"\nCalculation is currently RUNNING. "
            f"Poll again with: jobserver poll {updated_job.jobname}\n"
        )
    elif updated_job.status == STATUS_QUEUED:
        print(
            f"\nCalculation is currently QUEUED (waiting for free cores).\n"
        )
    elif updated_job.status == STATUS_COMPLETED:
        print("\n[SUCCESS] Calculation completed successfully!")
        print(f"Output files available in: {updated_job.local_dir}\n")
    elif updated_job.status == STATUS_FAILED:
        print("\n[FAILED] Calculation terminated with an error.")
        print("Last log lines:")
        print(transport.fetchLogs(updated_job, tail_lines=20))
        print()
    elif updated_job.status == STATUS_KILLED:
        print("\n[KILLED] Calculation was terminated by user.\n")

    return 0


def cmd_daemon(args, store, dispatcher):
    """
    Run autonomous background queue monitoring loop until all jobs finish.

    :param args: Parsed argparse namespace.
    :param store: JobStore instance.
    :param dispatcher: JobDispatcher instance.
    :return: Integer exit code.
    """
    watcher = JobWatcher(
        scheduler=dispatcher.scheduler,
        store=store,
        registry=dispatcher.registry,
    )
    watcher.runLoop(interval_seconds=args.interval)
    return 0


def cmd_logs(args, store, dispatcher):
    """
    Print the latest log lines for a calculation.

    :param args: Parsed argparse namespace.
    :param store: JobStore instance.
    :param dispatcher: JobDispatcher instance.
    :return: Integer exit code.
    """
    try:
        job = store.findJob(args.job_id or ".")
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}\n")
        return 1

    host_spec = dispatcher.registry.getHost(job.host)
    transport = dispatcher.getTransport(host_spec)

    lines = args.lines or 50
    print(f"\n--- Log for '{job.jobname}' (Last {lines} lines) ---")
    print(transport.fetchLogs(job, tail_lines=lines))
    return 0


def cmd_kill(args, store, dispatcher):
    """
    Terminate a running calculation.

    :param args: Parsed argparse namespace.
    :param store: JobStore instance.
    :param dispatcher: JobDispatcher instance.
    :return: Integer exit code.
    """
    try:
        job = store.findJob(args.job_id)
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}\n")
        return 1

    host_spec = dispatcher.registry.getHost(job.host)
    transport = dispatcher.getTransport(host_spec)

    success = transport.kill(job)
    if success:
        print(
            f"\n[SUCCESS] Terminated calculation '{job.jobname}' "
            f"(ID: {job.job_id}).\n"
        )
    else:
        print(
            f"\n[WARNING] Process for '{job.jobname}' was not active "
            f"or could not be terminated.\n"
        )
    return 0


def main(args=None):
    """
    Main entrypoint for jobserver CLI.

    :param args: Optional argument list.
    :return: Integer exit code.
    """
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="jobserver",
        description="JobServer: Compute orchestration and job management CLI.",
    )
    subparsers = parser.add_subparsers(
        dest="subcommand", help="Available subcommands"
    )

    # list
    subparsers.add_parser(
        "list", help="List all active and recent calculations"
    )

    # poll
    p_poll = subparsers.add_parser(
        "poll", help="Poll status and retrieve outputs"
    )
    p_poll.add_argument(
        "job_id", nargs="?", default=None, help="Job name or Job ID"
    )

    # daemon
    p_daemon = subparsers.add_parser(
        "daemon", help="Run background queue processing daemon"
    )
    p_daemon.add_argument(
        "--interval",
        dest="interval",
        type=int,
        default=3,
        help="Polling interval in seconds (default: 3)",
    )

    # logs
    p_logs = subparsers.add_parser(
        "logs", help="View trailing calculation logs"
    )
    p_logs.add_argument(
        "job_id", nargs="?", default=None, help="Job name or Job ID"
    )
    p_logs.add_argument(
        "-n",
        dest="lines",
        type=int,
        default=50,
        help="Lines to display (default: 50)",
    )

    # kill
    p_kill = subparsers.add_parser(
        "kill", help="Terminate a running calculation"
    )
    p_kill.add_argument("job_id", help="Job name or Job ID to terminate")

    parsed = parser.parse_args(args)

    if not parsed.subcommand:
        parser.print_help()
        return 0

    store = JobStore()
    dispatcher = JobDispatcher()

    if parsed.subcommand == "list":
        return cmd_list(parsed, store, dispatcher)
    elif parsed.subcommand == "poll":
        return cmd_poll(parsed, store, dispatcher)
    elif parsed.subcommand == "daemon":
        return cmd_daemon(parsed, store, dispatcher)
    elif parsed.subcommand == "logs":
        return cmd_logs(parsed, store, dispatcher)
    elif parsed.subcommand == "kill":
        return cmd_kill(parsed, store, dispatcher)

    return 0


if __name__ == "__main__":
    sys.exit(main())
