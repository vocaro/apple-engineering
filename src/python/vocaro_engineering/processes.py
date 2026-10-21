"""Bounded supervision of the process group this invocation creates."""
import os
import json
from pathlib import Path
import signal
import subprocess
import time


def snapshot():
    output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pgid=,lstart="], text=True)
    result = {}
    for line in output.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4:
            result[int(parts[0])] = (int(parts[1]), int(parts[2]), parts[3])
    return result


def supervise(command, *, cwd, stdout=None, timeout=None, env=None):
    """Wait for the owned root and observed descendants, including separate process groups.

    PID start identities prevent signalling a reused PID. An uncertain or interrupted run
    raises so admission retains its orphan guard. A confirmed terminal exit keeps its status.
    """
    environment = dict(os.environ) if env is None else env
    token = json.loads(environment.get("VOCARO_RESOURCE_TOKEN", "{}"))
    descriptors = tuple(item["fd"] for item in token.get("locks", []))
    child = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stdout,
        stderr=subprocess.STDOUT if stdout is not None else None, start_new_session=True,
        pass_fds=descriptors)
    known, born = {}, None
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
                pid for pid, birth in known.items() if pid in current and current[pid][2] == birth}
            if root_active:
                for pid, (_parent, group, birth) in current.items():
                    if pid != child.pid and group == child.pid:
                        known[pid] = birth
                        parents.add(pid)
            while True:
                added = {pid for pid, (parent, _group, _birth) in current.items()
                         if parent in parents and pid not in parents}
                if not added: break
                parents.update(added)
                known.update({pid: current[pid][2] for pid in added})
            live = {pid for pid, birth in known.items() if pid in current and current[pid][2] == birth}
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
