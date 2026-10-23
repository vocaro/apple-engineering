"""The build host's side of `eng remote`, sent over SSH and run there by the host's own Python.

It imports nothing from the toolkit, because it runs before the toolkit is checked out there,
and Python 3.9, a Mac's system Python, runs it. It claims a persistent checkout of the project,
places the dispatched commits, and runs `eng run` or `eng admit` there under the build host's
own heavy-work admission. Standard output carries framed lines: `O` for output, `L` for the
lane's log as it grows, and a closing `R` with the result as JSON. Standard input is the
dispatcher's lifeline: its end, which a stop, the dispatcher's death or a dropped connection
sends, stops the run as a stop signal stops a local one.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

# Seconds between reports while every checkout is in use, and before waiting for one gives up.
REPORT_SECONDS, CLAIM_TIMEOUT = 300, 5400
# Seconds the output of a finished command may take to drain: a descendant can hold the pipe.
DRAIN_SECONDS = 5

_output = threading.Lock()
_stop = threading.Event()


def emit(kind, data):
    """Write one framed line. A closed connection is a stop: nobody is left to read the result."""
    if not data.endswith(b"\n"): data += b"\n"
    with _output:
        try:
            sys.stdout.buffer.write(kind + b" " + data)
            sys.stdout.buffer.flush()
        except OSError:
            _stop.set()


def say(text):
    emit(b"O", f"build-host: {text}".encode())


def output(command, environment=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def identity(developer_dir):
    """The Mac a result was measured on, its macOS and the Xcode at developer_dir."""
    xcode = None
    if developer_dir and Path(developer_dir).is_dir():
        xcode = output(["xcrun", "xcodebuild", "-version"], {**os.environ, "DEVELOPER_DIR": developer_dir})
    number = lambda name: int(output(["sysctl", "-n", name]) or 0) or None
    return {"name": output(["scutil", "--get", "LocalHostName"]) or os.uname().nodename,
            "model": output(["sysctl", "-n", "hw.model"]), "cpus": number("hw.ncpu"),
            "memoryBytes": number("hw.memsize"), "macOS": output(["sw_vers", "-productVersion"]),
            "build": output(["sw_vers", "-buildVersion"]), "developerDir": developer_dir, "xcode": xcode}


def git(*arguments, cwd=None):
    result = subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def changes(checkout):
    """Tracked changes and nonignored untracked files, which a run left in a checkout."""
    return git("status", "--porcelain", "--untracked-files=normal", cwd=checkout) if checkout.exists() else ""


def claim(base, count, directory):
    """Lock a free checkout slot without changes, waiting while every one is in use.

    The lock is an flock the run's command inherits, so it holds while that command lives. A
    checkout with changes is left as it is, for inspection, and passed over.
    """
    base.mkdir(parents=True, exist_ok=True)
    started, reported, named = time.monotonic(), None, set()
    while not _stop.is_set():
        changed = 0
        for index in range(count):
            descriptor = os.open(base / f"{index}.lock", os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(descriptor)
                continue
            checkout = base / str(index) / directory
            left = changes(checkout)
            if not left:
                return index, descriptor
            os.close(descriptor)
            changed += 1
            if index not in named:
                say(f"passing over {checkout}, which a run left with changes:\n{left}")
                named.add(index)
        if changed == count:
            raise RuntimeError(f"every checkout under {base} has changes a run left; inspect and remove them")
        waited = int(time.monotonic() - started)
        if waited >= CLAIM_TIMEOUT:
            raise RuntimeError(f"no checkout of {directory} came free in {CLAIM_TIMEOUT}s")
        if reported is None or waited - reported >= REPORT_SECONDS:
            say(f"waiting ({waited}s): every checkout of {directory} is in use")
            reported = waited
        time.sleep(1)
    return None


def place(repository, checkout, commit, ref, origin=None):
    """Check commit out, detached, in a persistent worktree whose ignored inputs and builds stay.

    Only the toolkit names an origin: a heavy lane's policy refresh fetches it."""
    if origin and output(["git", "--git-dir", str(repository), "config", "--get", "remote.origin.url"]) != origin:
        git("--git-dir", str(repository), "config", "remote.origin.url", origin)
    if checkout.exists():
        git("checkout", "--detach", "--quiet", commit, cwd=checkout)
    else:
        git("--git-dir", str(repository), "worktree", "prune")
        git("--git-dir", str(repository), "worktree", "add", "--detach", "--quiet", str(checkout), commit)
    if git("rev-parse", "HEAD", cwd=checkout) != commit:
        raise RuntimeError(f"{checkout} is not at {commit}")
    # The detached worktree keeps the commit reachable; the pushed ref only carried it here.
    subprocess.run(["git", "--git-dir", str(repository), "update-ref", "-d", ref], capture_output=True)


def relay(stream):
    for line in iter(stream.readline, b""):
        emit(b"O", line)


def follow(path, done):
    """Send the lane's log from its start as it grows. The lane creates it afresh."""
    stream, pending = None, b""
    try:
        while True:
            finished = done.is_set()
            if stream is None:
                try: stream = path.open("rb")
                except FileNotFoundError: pass
            if stream is not None:
                *lines, pending = (pending + stream.read()).split(b"\n")
                for line in lines: emit(b"L", line)
            if finished: break
            time.sleep(0.2)
    finally:
        if stream is not None: stream.close()
    if pending: emit(b"L", pending)


def step(command, checkout, environment, lock, log):
    """Run one eng command; a stop sends it SIGTERM, which it carries out as a supervised stop."""
    if log is not None: log.unlink(missing_ok=True)
    child = subprocess.Popen(command, cwd=checkout, env=environment, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                             pass_fds=(lock,))
    done = threading.Event()
    threads = [threading.Thread(target=relay, args=(child.stdout,), daemon=True)]
    if log is not None: threads.append(threading.Thread(target=follow, args=(log, done), daemon=True))
    for thread in threads: thread.start()
    forwarded = False
    while child.poll() is None:
        if _stop.is_set() and not forwarded:
            say("stop requested; sending SIGTERM to the run, which stops its command and leaves admission")
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            forwarded = True
        time.sleep(0.1)
    done.set()
    for thread in threads: thread.join(DRAIN_SECONDS)
    return child.returncode


def watch():
    """The end of standard input is the dispatcher's stop.

    It reads the descriptor, not sys.stdin: Python 3.9 aborts at exit when a daemon thread is
    blocked holding the buffered reader's lock (observed on macOS 27.2, October 2026)."""
    try:
        while os.read(0, 65536): pass
    except OSError:
        pass
    _stop.set()


def main(plan):
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, lambda *_: _stop.set())
    threading.Thread(target=watch, daemon=True).start()
    result = {"started": time.time(), "exitStatus": None, "stopped": False,
              "host": identity(plan.get("developerDir"))}
    try:
        expected, found = plan.get("xcode"), result["host"]["xcode"]
        if expected and found != expected:
            raise RuntimeError(f"the Xcode at {plan['developerDir']} is {found or 'missing'}, not the dispatcher's "
                               f"{expected}; install the same Xcode there or select it with DEVELOPER_DIR")
        root, project, toolkit = Path.home() / plan["root"], plan["project"], plan.get("toolkit")
        base = root / "checkouts" / project["directory"]
        claimed = claim(base, plan["checkouts"], project["directory"])
        if claimed is None:
            result["stopped"] = True
            return result
        index, lock = claimed
        checkout = base / str(index) / project["directory"]
        place(root / project["repository"], checkout, project["commit"], project["ref"], project.get("origin"))
        kit = checkout
        if toolkit is not None:
            kit = base / str(index) / toolkit["directory"]
            place(root / toolkit["repository"], kit, toolkit["commit"], toolkit["ref"], toolkit.get("origin"))
        result.update(checkout=str(checkout), slot=index)
        say(f"{checkout} at {project['commit'][:12]}")
        environment = {**os.environ, "VOCARO_ENGINEERING_ROOT": str(kit)}
        if plan.get("developerDir"): environment["DEVELOPER_DIR"] = plan["developerDir"]
        eng = [sys.executable, str(kit / "bin/eng"), "--project", str(checkout)]
        steps = [("provision", [*eng, "run", "provision"], checkout / ".build/engineering/provision/run.log")] \
            if plan.get("provision") else []
        steps.append(("work", [*eng, *plan["work"]], checkout / plan["log"] if plan.get("log") else None))
        for stage, command, log in steps:
            if _stop.is_set(): break
            result.update(stage=stage, exitStatus=step(command, checkout, environment, lock, log))
            if result["exitStatus"] != 0: break
        result["stopped"] = _stop.is_set()
        receipt = checkout / plan["receipt"]
        # A command that failed before it wrote a receipt leaves the previous run's in place.
        if receipt.is_file() and receipt.stat().st_mtime >= result["started"]:
            result["receipt"] = json.loads(receipt.read_text())
    except (OSError, RuntimeError, ValueError) as error:
        result["error"] = str(error)
    finally:
        result["finished"] = time.time()
        emit(b"R", json.dumps(result).encode())
    return result


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
