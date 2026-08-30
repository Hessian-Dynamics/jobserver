"""
Unit tests for HostRegistry configuration loading and validation.
"""

import pytest

from jobserver.core.registry import HostRegistry


def test_default_localhost_registry(tmp_path):
    # Non-existent config path should fall back to default localhost
    non_existent = tmp_path / "hosts.toml"
    reg = HostRegistry(config_path=non_existent)

    assert "localhost" in reg.listHosts()
    spec = reg.getHost("localhost")
    assert spec["type"] == "local"
    assert spec["max_cores"] > 0


def test_custom_hosts_toml(tmp_path):
    config_file = tmp_path / "hosts.toml"
    config_content = """
    [hosts.cluster01]
    type = "ssh"
    hostname = "cluster01.lab.edu"
    username = "chem_user"
    max_cores = 64
    remote_scratch = "/scratch/chem_user"
    """
    config_file.write_text(config_content)

    reg = HostRegistry(config_path=config_file)
    assert "cluster01" in reg.listHosts()
    assert "localhost" in reg.listHosts()

    spec, effective = reg.validateHost("cluster01", requested_cores=32)
    assert effective == 32
    assert spec["hostname"] == "cluster01.lab.edu"

    # Clamp cores if exceeding max_cores
    _, effective_clamped = reg.validateHost("cluster01", requested_cores=128)
    assert effective_clamped == 64


def test_invalid_host_raises():
    reg = HostRegistry()
    with pytest.raises(KeyError):
        reg.getHost("non_existent_cluster")
