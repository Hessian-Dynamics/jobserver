"""
Unit tests for JobControl argument parsing and host specification.
"""

from jobserver.core.jobcontrol import (
    DEFAULT_HOST,
    DEFAULT_SUBHOST,
    extractJobControlArgs,
    parseHostSpec,
    resolveJobName,
)


def test_parse_host_spec():
    assert parseHostSpec("localhost:10") == ("localhost", 10)
    assert parseHostSpec("cluster01:32") == ("cluster01", 32)
    assert parseHostSpec("node01") == ("node01", None)
    assert parseHostSpec(None) == (DEFAULT_HOST, None)


def test_resolve_job_name():
    assert resolveJobName("explicit_name", "input.xyz") == "explicit_name"
    assert resolveJobName(None, "ethanol.xyz") == "ethanol"
    assert resolveJobName(None, "/path/to/strained_h2o.xyz") == "strained_h2o"
    auto_name = resolveJobName(None, None)
    assert auto_name.startswith("job_")


def test_extract_job_control_args():
    raw = [
        "-i",
        "ethanol.xyz",
        "-JOBNAME",
        "eth_md",
        "-HOST",
        "cluster01:16",
        "-SUBHOST",
        "node02:8",
        "-time",
        "10.0",
        "-temp",
        "350.0",
    ]
    control, driver_args = extractJobControlArgs(raw)

    assert control["jobname"] == "eth_md"
    assert control["host"] == "cluster01:16"
    assert control["subhost"] == "node02:8"
    assert control["input"] == "ethanol.xyz"
    assert driver_args == [
        "-i",
        "ethanol.xyz",
        "-time",
        "10.0",
        "-temp",
        "350.0",
    ]


def test_extract_job_control_defaults():
    raw = ["-i", "water.xyz", "-time", "5.0"]
    control, driver_args = extractJobControlArgs(raw)

    assert control["jobname"] == "water"
    assert control["host"] == DEFAULT_HOST
    assert control["subhost"] == DEFAULT_SUBHOST
    assert driver_args == ["-i", "water.xyz", "-time", "5.0"]
