"""
Host registry and configuration loader for certified computing environments.
"""

import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG_LOCATIONS = [
    Path("hosts.toml"),
    Path.home() / ".jobserver" / "hosts.toml",
]


class HostRegistry:
    """
    Manages certified host definitions loaded from hosts.toml config files.
    """

    def __init__(self, config_path=None):
        """
        Initialize HostRegistry.

        :param config_path: Optional explicit path to hosts.toml file.
        """
        self.config_path = Path(config_path) if config_path else None
        self.hosts = {}
        self.loadConfig()

    def loadConfig(self):
        """
        Load host configurations from file or initialize defaults.
        """
        target_path = None
        if self.config_path and self.config_path.is_file():
            target_path = self.config_path
        else:
            for loc in DEFAULT_CONFIG_LOCATIONS:
                if loc.is_file():
                    target_path = loc
                    break

        if target_path:
            with open(target_path, "rb") as f:
                data = tomllib.load(f)
                self.hosts = data.get("hosts", {})

        # Ensure default localhost entry is always present
        if "localhost" not in self.hosts:
            self.hosts["localhost"] = {
                "type": "local",
                "max_cores": os.cpu_count() or 4,
                "scratch_dir": "./",
            }

    def getHost(self, host_name):
        """
        Retrieve host configuration by name.

        :param host_name: Name of registered host (e.g. 'localhost').
        :return: Host configuration dictionary.
        """
        name = host_name or "localhost"
        if name not in self.hosts:
            raise KeyError(
                f"Host '{name}' is not registered in hosts configuration.\n"
                f"Available hosts: {list(self.hosts.keys())}"
            )
        return self.hosts[name]

    def listHosts(self):
        """
        List all registered host names.

        :return: List of host name strings.
        """
        return list(self.hosts.keys())

    def validateHost(self, host_name, requested_cores=None):
        """
        Validate host exists and requested cores are within hardware limits.

        :param host_name: Name of host to validate.
        :param requested_cores: Optional requested physical core count.
        :return: Tuple of (host_spec, effective_cores).
        """
        spec = self.getHost(host_name)
        max_cores = spec.get("max_cores", os.cpu_count() or 4)

        if requested_cores is not None:
            if requested_cores > max_cores:
                effective_cores = max_cores
            else:
                effective_cores = max(1, requested_cores)
        else:
            effective_cores = max_cores

        return spec, effective_cores
