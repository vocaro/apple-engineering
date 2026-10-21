"""Heavy-work admission interoperating with the existing PDF and StudyWright locks.

The bridge holds StudyWright's shlock while publishing a guard; old gate/warm-push callers
already wait on that guard. Exclusive work holds every old PDF slot. Crashed owners retain
their guard for explicit inspection rather than treating a deadline as release.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

TOKEN = "VOCARO_RESOURCE_TOKEN"


def process_start(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def slot_directory():
    return Path(os.environ.get("HEAVY_SLOT_DIR") or Path(tempfile.gettempdir()) / "pdfreflow-heavy-slots")


def take_slot(directory, slots):
    """Compatibility API: one old-style slot descriptor, or None."""
    for slot in range(slots):
        fd = os.open(Path(directory) / f"slot{slot}", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        return slot, fd
    return None


def inherited(exclusive=False):
    raw = os.environ.get(TOKEN)
    if not raw:
        return False
    try:
        token = json.loads(raw)
        if token.get("schemaVersion") != 1 or not token.get("locks"):
            raise ValueError("Invalid admission token")
        for item in token["locks"]:
            held, path = os.fstat(item["fd"]), os.stat(item["path"])
            if (held.st_dev, held.st_ino) != (path.st_dev, path.st_ino):
                raise ValueError("Admission descriptor does not match its lock")
            if item["nonce"] not in os.pread(item["fd"], 4096, 0).decode():
                raise ValueError("Admission owner changed")
        if exclusive and not token.get("exclusive"):
            raise ValueError("Cannot acquire exclusive admission inside shared admission")
        return True
    except (KeyError, TypeError, OSError, ValueError) as error:
        raise RuntimeError(f"Invalid inherited resource admission: {error}") from error


class Admission:
    def __init__(self, label, exclusive=False, timeout=5400):
        self.label, self.exclusive, self.timeout = label, exclusive, timeout
        self.directory = slot_directory()
        self.slots = int(os.environ.get("HEAVY_SLOTS", "3"))
        self.poll = float(os.environ.get("HEAVY_POLL_SECONDS", "1"))
        if self.slots < 1 or self.poll <= 0 or timeout < 0:
            raise ValueError("Invalid resource limits")
        self.legacy = Path(os.environ.get("SW_GATE_LOCK_FILE", "/tmp/studywright-gate-suite.lock"))
        self.guard = Path(str(self.legacy) + ".warm-push-guard")
        self.identity = uuid.uuid4().hex
        self.descriptors = []
        self.previous = None
        self.reused = False

    def _guard(self):
        if not self.guard.exists():
            return {"vocaroEngineering": 1, "owners": {}}
        try:
            value = json.loads(self.guard.read_text())
        except (OSError, ValueError):
            return None
        if value.get("vocaroEngineering") != 1:
            return None
        # Never reclaim a disappeared owner: its children may still use a different session.
        for owner in value.get("owners", {}).values():
            if owner.get("uncertain") or process_start(owner["pid"]) != owner.get("start"):
                return None
            try:
                os.kill(owner["pid"], 0)
            except ProcessLookupError:
                return None
        return value

    def _legacy_lock(self):
        if Path("/usr/bin/shlock").is_file():
            return subprocess.run(["/usr/bin/shlock", "-f", str(self.legacy), "-p", str(os.getpid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        return not self.legacy.exists()

    def _unlock_legacy(self):
        if self.legacy.exists() and self.legacy.read_text().strip() == str(os.getpid()):
            self.legacy.unlink()

    def _attempt(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "coordination.lock").open("a+") as bridge:
            fcntl.flock(bridge, fcntl.LOCK_EX)
            state = self._guard()
            if state is None:
                return False
            if not self._legacy_lock():
                return False
            try:
                for _ in range(self.slots if self.exclusive else 1):
                    taken = take_slot(self.directory, self.slots)
                    if taken is None:
                        for _slot, fd in self.descriptors:
                            os.close(fd)
                        self.descriptors = []
                        return False
                    self.descriptors.append(taken)
                born = process_start(os.getpid())
                if born is None:
                    for _slot, fd in self.descriptors: os.close(fd)
                    self.descriptors = []
                    raise RuntimeError("Cannot establish the admission owner's process identity")
                state["owners"][self.identity] = {"pid": os.getpid(), "start": born, "label": self.label,
                                                    "exclusive": self.exclusive}
                # A legacy keeper cannot obtain shlock until this publication finishes.
                self.guard.write_text(json.dumps(state) + "\n")
                locks = []
                for slot, fd in self.descriptors:
                    os.ftruncate(fd, 0)
                    os.write(fd, f"{os.getpid()} {self.identity} {self.label[:160]}\n".encode())
                    os.set_inheritable(fd, True)
                    locks.append({"fd": fd, "path": str(self.directory / f"slot{slot}"), "nonce": self.identity})
                self.previous = os.environ.get(TOKEN)
                os.environ[TOKEN] = json.dumps({"schemaVersion": 1, "exclusive": self.exclusive, "locks": locks})
                return True
            finally:
                self._unlock_legacy()

    def __enter__(self):
        if inherited(self.exclusive):
            self.reused = True
            return self
        started = time.monotonic()
        reported = None
        while not self._attempt():
            waited = int(time.monotonic() - started)
            if reported is None or waited - reported >= 300:
                print(f"heavy: all {self.slots} slots busy or reserved, waiting ({waited}s)", file=sys.stderr, flush=True)
                reported = waited
            if time.monotonic() - started >= self.timeout:
                raise TimeoutError("Resource queue busy or an orphan requires inspection; no lock was reclaimed")
            time.sleep(self.poll)
        print(f"heavy: slot {','.join(str(slot) for slot, _fd in self.descriptors)} after {int(time.monotonic() - started)}s: {self.label[:160]}", file=sys.stderr, flush=True)
        return self

    def __exit__(self, kind, _value, _traceback):
        if self.reused:
            return False
        if self.previous is None: os.environ.pop(TOKEN, None)
        else: os.environ[TOKEN] = self.previous
        with (self.directory / "coordination.lock").open("a+") as bridge:
            fcntl.flock(bridge, fcntl.LOCK_EX)
            for _slot, fd in self.descriptors:
                os.close(fd)
            # An exception may leave unobserved children. Retain the guard for inspection.
            state = self._guard()
            if state is not None:
                if kind is None:
                    state["owners"].pop(self.identity, None)
                    if state["owners"]: self.guard.write_text(json.dumps(state) + "\n")
                    else: self.guard.unlink(missing_ok=True)
                else:
                    state["owners"][self.identity]["uncertain"] = True
                    self.guard.write_text(json.dumps(state) + "\n")
        return False


@contextlib.contextmanager
def heavy_slot(label, *, exclusive=False, timeout=5400):
    with Admission(label, exclusive, timeout):
        yield


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exclusive", action="store_true")
    parser.add_argument("--timeout", type=float, default=5400)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command: parser.error("a command is required")
    with Admission(" ".join(command), args.exclusive, args.timeout):
        environment = dict(os.environ)
        if args.exclusive:
            # The outer admission owns the legacy guard; do not acquire it again in a shell.
            environment["SW_GATE_LOCK"] = "0"
        from vocaro_engineering.processes import supervise
        return supervise(command, cwd=Path.cwd(), env=environment)


def json_descriptors():
    token = json.loads(os.environ[TOKEN])
    return [(index, item["fd"]) for index, item in enumerate(token["locks"])]


if __name__ == "__main__":
    raise SystemExit(main())
