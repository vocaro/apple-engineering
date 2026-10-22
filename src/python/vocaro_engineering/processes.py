"""Bounded supervision of the process group this invocation creates."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

# Seconds an observed descendant may outlive the root before it is stopped, and then before
# SIGTERM becomes SIGKILL. Xcode's DTServiceHub can outlive xcodebuild by minutes, ignoring SIGTERM.
LINGER, KILL_AFTER = 60, 10


def snapshot():
    output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pgid=,lstart="], text=True)
    result = {}
    for line in output.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4:
            result[int(parts[0])] = (int(parts[1]), int(parts[2]), parts[3])
    return result


def describe(pids, known, root):
    """The processes still running after the root, with the parent and group each was first seen with."""
    pids = sorted(pids)
    listing = subprocess.run(["ps", "-o", "pid,ppid,pgid,lstart,args", "-p", ",".join(map(str, pids))],
                             capture_output=True, text=True).stdout.rstrip()
    seen = "; ".join(f"{pid} with parent {known[pid][0]}, group {known[pid][1]}" for pid in pids)
    return (f"supervise: stopping {len(pids)} process(es) still running {LINGER:g}s after the command "
            f"(PID {root}) exited, with SIGTERM, then SIGKILL after {KILL_AFTER:g}s; first seen: {seen}\n{listing}")


class NotStarted(OSError):
    """The command could not be started, so it left no process to wait for."""


def supervise(command, *, cwd, stdout=None, timeout=None, env=None):
    """Wait for the owned root and observed descendants, including separate process groups.

    PID start identities prevent signalling a reused PID. An uncertain or interrupted run
    raises so admission retains its orphan guard. A confirmed terminal exit keeps its status.
    Descendants still running LINGER seconds after the root exits are reported on stderr and
    stopped; the root's status stands once they are gone, and one that survives SIGKILL is
    still awaited. A command that cannot start raises NotStarted, which admission releases.
    """
    environment = dict(os.environ) if env is None else env
    token = json.loads(environment.get("VOCARO_RESOURCE_TOKEN", "{}"))
    descriptors = tuple(item["fd"] for item in token.get("locks", []))
    try:
        child = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stdout,
            stderr=subprocess.STDOUT if stdout is not None else None, start_new_session=True,
            pass_fds=descriptors)
    except (OSError, ValueError) as error:
        # Popen reaps a child whose exec failed before it raises; nothing else ran.
        raise NotStarted(f"Command did not start: {error}") from error
    # Each observed descendant's (parent, group, start) when first seen, for its identity and report.
    known, born, exited, stopping = {}, None, None, set()
    started = time.monotonic()
    expired = False
    try:
        while True:
            current = snapshot()
            row = current.get(child.pid)
            if born is None and child.returncode is None and row is not None and row[:2] == (os.getpid(), child.pid):
                born = row[2]
            root_active = child.returncode is None and row == (os.getpid(), child.pid, born)
            parents = ({child.pid} if root_active else set()) | {
                pid for pid, seen in known.items() if pid in current and current[pid][2] == seen[2]}
            if root_active:
                for pid, (_parent, group, _birth) in current.items():
                    if pid not in parents and group == child.pid:
                        known[pid] = current[pid]
                        parents.add(pid)
            while True:
                added = {pid for pid, (parent, _group, _birth) in current.items()
                         if parent in parents and pid not in parents}
                if not added: break
                parents.update(added)
                known.update({pid: current[pid] for pid in added})
            live = {pid for pid, seen in known.items() if pid in current and current[pid][2] == seen[2]}
            if timeout is not None and time.monotonic() - started >= timeout:
                expired = True
                if root_active:
                    try: os.killpg(child.pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError): pass
                for pid in live:
                    try: os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError): pass
            result = child.poll()
            if result is not None and not live:
                if expired: raise TimeoutError(f"Owned command timed out after {timeout}s: {command[0]}")
                return result
            if result is not None and not expired:
                if exited is None: exited = time.monotonic()
                overdue = time.monotonic() - exited - LINGER
                if overdue >= 0:
                    # SIGTERM once for each process, then SIGKILL, which cannot be caught, until it is gone.
                    fresh = {pid for pid in live if (pid, known[pid][2]) not in stopping}
                    if fresh: print(describe(fresh, known, child.pid), file=sys.stderr, flush=True)
                    stopping.update((pid, known[pid][2]) for pid in fresh)
                    for pid in live if overdue >= KILL_AFTER else fresh:
                        try: os.kill(pid, signal.SIGKILL if overdue >= KILL_AFTER else signal.SIGTERM)
                        except (ProcessLookupError, PermissionError): pass
            if expired and time.monotonic() - started > timeout + 15:
                raise RuntimeError("Owned descendants have no confirmed terminal result; reservation retained")
            time.sleep(0.05)
    finally:
        stop(child)


def stop(process):
    if process.poll() is not None:
        return
    for sig, limit in [(signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=limit)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError(f"Owned process {process.pid} has no confirmed terminal result")


def run(command, *, cwd, log_path, timeout=None, env=None):
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as log:
        return supervise(command, cwd=cwd, stdout=log, timeout=timeout, env=env)
