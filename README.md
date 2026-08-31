# jobserver

**Autonomous compute orchestration, hardware pinning, and queue management.**

`jobserver` is a lightweight, strictly independent infrastructure layer that manages the execution lifecycle of intensive computational tasks. It abstracts away OS-level process management, thread pinning, and resource queuing, allowing physics engines to execute in clean, isolated environments.

## Core Capabilities

1. **Hardware Affinity:** Automatically computes available hardware limits and injects OpenMP/MKL thread pinning (`OMP_PLACES=cores`) to prevent CPU context-thrashing and maximize L3 cache utilization.
2. **Slot-Based Queueing:** Enforces strict physical core budgets. If a requested allocation (e.g., 8 cores) exceeds the currently available budget, the calculation is held in a precise FIFO queue.
3. **Autonomous Watcher Daemon:** A self-terminating background process (`jobserver daemon`) that silently polls running jobs and automatically promotes queued jobs the millisecond CPU cores become available.
4. **Sandboxed Execution:** Ensures every calculation executes within a dedicated, isolated directory, completely decoupling the submitter terminal from the background worker.

## CLI Usage

The `jobserver` CLI acts as your control plane for all active calculations across your compute nodes.

```bash
# List all active, queued, and recently completed calculations
jobserver list

# Poll the live status of a specific job (and auto-fetch artifacts)
jobserver poll sim_01

# Tail the live log output of a running job
jobserver logs sim_01 -n 100

# Send a POSIX kill signal to terminate a runaway job
jobserver kill sim_01
```

## System Configuration

Host capacity and hardware limits are controlled via `~/.jobserver/hosts.toml`. 

```toml
[hosts.localhost]
type = "local"
max_cores = 16
```
