"""Heavy-work admission interoperating with the existing PDF and StudyWright locks.

The bridge holds StudyWright's shlock while publishing a guard; old gate/warm-push callers
already wait on that guard. Exclusive work holds every old PDF slot. Crashed owners retain
their guard for explicit inspection rather than treating a deadline as release.

HEAVY_SLOTS jobs are always admitted. More, up to HEAVY_SLOTS_MAX, are admitted one at a time
while the load average and memory pressure show spare capacity: a fixed count left the host
idle behind jobs waiting on simulators, while ten unqueued builds starved watchdogd until the
kernel panicked (2026-10-14). Admission cannot preempt a job that becomes heavy later.
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
    if os.environ.get("HEAVY_SLOT_DIR"):
        return Path(os.environ["HEAVY_SLOT_DIR"])
    # Preserve the legacy macOS user-temp namespace even when a command uses a private TMPDIR.
    # A process-local temporary directory must not create another host-wide build budget.
    if sys.platform == "darwin":
        base = subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True, timeout=5).strip()
        if not base:
            raise RuntimeError("Cannot establish the host resource directory")
        return Path(base) / "pdfreflow-heavy-slots"
    return Path("/tmp/pdfreflow-heavy-slots")


def take_slot(directory, slots, start=0):
    """Compatibility API: one old-style slot descriptor, or None."""
    for slot in range(start, slots):
        fd = os.open(Path(directory) / f"slot{slot}", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        return slot, fd
    return None


def last_admission(directory, slots):
    """When a holder last wrote its identity into a slot. Probing leaves new slot files empty."""
    latest = 0
    for slot in range(slots):
        try:
            status = (Path(directory) / f"slot{slot}").stat()
        except FileNotFoundError:
            continue
        if status.st_size:
            latest = max(latest, status.st_mtime)
    return latest


def memory_normal():
    """Whether macOS reports normal memory pressure: level 1, where 2 is warning and 4 critical."""
    if sys.platform != "darwin":
        return False
    result = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "1"


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
        nonces = {item["nonce"] for item in token["locks"]}
        if len(nonces) != 1:
            raise ValueError("Admission descriptors have different owners")
        legacy = os.environ.get("SW_GATE_LOCK_FILE", "/tmp/studywright-gate-suite.lock")
        guard = Path(token.get("guard", legacy + ".warm-push-guard"))
        state = json.loads(guard.read_text())
        owner = state.get("owners", {}).get(next(iter(nonces)))
        if state.get("vocaroEngineering") != 1 or not owner or owner.get("uncertain"):
            raise ValueError("Admission owner has no active guard")
        if process_start(owner["pid"]) != owner.get("start"):
            raise ValueError("Admission owner identity changed")
        if bool(token.get("exclusive")) != bool(owner.get("exclusive")):
            raise ValueError("Admission capability differs from its owner")
        if exclusive and not owner.get("exclusive"):
            raise ValueError("Cannot acquire exclusive admission inside shared admission")
        return True
    except (KeyError, TypeError, OSError, ValueError) as error:
        raise RuntimeError(f"Invalid inherited resource admission: {error}") from error


def publish_guard(path, state):
    """Readers authenticate without the coordination lock, so publication is atomic."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".vocaro-guard-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Admission:
    def __init__(self, label, exclusive=False, timeout=5400):
        self.label, self.exclusive, self.timeout = label, exclusive, timeout
        self.directory = slot_directory()
        cores = os.cpu_count() or 1
        self.slots = int(os.environ.get("HEAVY_SLOTS", "3"))
        self.maximum = int(os.environ.get("HEAVY_SLOTS_MAX", max(self.slots, cores // 2)))
        self.load_limit = float(os.environ.get("HEAVY_LOAD_LIMIT", 0.75 * cores))
        # The one-minute load average shows a new job's load only gradually.
        self.settle = float(os.environ.get("HEAVY_SETTLE_SECONDS", "30"))
        self.poll = float(os.environ.get("HEAVY_POLL_SECONDS", "1"))
        if self.slots < 1 or self.maximum < self.slots or self.settle < 0 or self.poll <= 0 or timeout < 0:
            raise ValueError("Invalid resource limits")
        self.waiting = None
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

    def _extra_refusal(self):
        if self.maximum == self.slots:
            return "no adaptive slots are configured"
        settling = time.time() - last_admission(self.directory, self.maximum)
        if settling < self.settle:
            return f"the load does not yet show the job admitted {int(settling)}s ago"
        try:
            load = os.getloadavg()[0]
        except OSError:
            return "the load average is unavailable"
        if load >= self.load_limit:
            return f"load {load:.1f} is at or above {self.load_limit:g}"
        if not memory_normal():
            return "memory pressure is not normal"
        return None

    def _extra_slot(self):
        """A slot beyond the guaranteed ones while the host shows spare capacity, or None."""
        refusal = self._extra_refusal()
        if refusal is None:
            taken = take_slot(self.directory, self.maximum, start=self.slots)
            if taken is not None:
                return taken
            refusal = f"all {self.maximum} slots are busy"
        self.waiting = f"all {self.slots} guaranteed slots are busy and {refusal}"
        return None

    def _attempt(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "coordination.lock").open("a+") as bridge:
            fcntl.flock(bridge, fcntl.LOCK_EX)
            state = self._guard()
            if state is None:
                self.waiting = "a foreign, dead or uncertain guard owner requires inspection"
                return False
            if not self._legacy_lock():
                self.waiting = "a legacy gate holds its lock"
                return False
            try:
                for _ in range(self.maximum if self.exclusive else 1):
                    taken = take_slot(self.directory, self.maximum if self.exclusive else self.slots)
                    if taken is None and not self.exclusive:
                        taken = self._extra_slot()
                    if taken is None:
                        if self.exclusive:
                            self.waiting = f"exclusive work needs all {self.maximum} slots free"
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
                publish_guard(self.guard, state)
                locks = []
                for slot, fd in self.descriptors:
                    os.ftruncate(fd, 0)
                    os.write(fd, f"{os.getpid()} {self.identity} {self.label[:160]}\n".encode())
                    os.set_inheritable(fd, True)
                    locks.append({"fd": fd, "path": str(self.directory / f"slot{slot}"), "nonce": self.identity})
                self.previous = os.environ.get(TOKEN)
                os.environ[TOKEN] = json.dumps({"schemaVersion": 1, "exclusive": self.exclusive, "guard": str(self.guard), "locks": locks})
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
                print(f"heavy: waiting ({waited}s): {self.waiting}", file=sys.stderr, flush=True)
                reported = waited
            if time.monotonic() - started >= self.timeout:
                raise TimeoutError(f"Resource queue busy or an orphan requires inspection ({self.waiting}); no lock was reclaimed")
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
                    if state["owners"]: publish_guard(self.guard, state)
                    else: self.guard.unlink(missing_ok=True)
                else:
                    state["owners"][self.identity]["uncertain"] = True
                    publish_guard(self.guard, state)
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
        from vocaro_engineering.processes import supervise
        return supervise(command, cwd=Path.cwd(), env=environment)


def json_descriptors():
    token = json.loads(os.environ[TOKEN])
    return [(index, item["fd"]) for index, item in enumerate(token["locks"])]


if __name__ == "__main__":
    raise SystemExit(main())
