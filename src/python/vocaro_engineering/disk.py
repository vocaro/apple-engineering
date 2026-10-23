"""Inventory of disk space on the shared host, and removal only of what nobody owns.

`eng disk` measures linked worktrees, simulators and their runtimes, build caches, results and
the other large directories, and classifies each item:

- candidate: the rules prove that no session's live work is in it. `--delete` removes it after
  the owner confirms its category on a terminal, checking it again first.
- owner: nothing shows a session using it, but only the owner can say whether it is still
  wanted. The command that would remove it is printed; `--delete` never runs it.
- kept: it is in use, owned, of unclear ownership, or holds work or evidence.

Without --delete nothing is changed. guides/shared-host.md § Reclaiming disk space has the rules.
"""
import argparse
from dataclasses import asdict, dataclass, field
import datetime
import glob
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import time

from . import devices as device_record

CANDIDATE, OWNER, KEPT = "candidate", "owner", "kept"
STATUS_ORDER = {CANDIDATE: 0, OWNER: 1, KEPT: 2}
CATEGORIES = {"worktree": "Linked worktrees", "simulator": "Simulators", "runtime": "Simulator runtimes",
              "derived-data": "Xcode DerivedData", "scratch": "Scratch builds outside checkouts",
              "swiftpm-cache": "SwiftPM shared cache", "archive": "Xcode archives",
              "results": "Result directories", "other": "Other large directories (never candidates)"}
UUID = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", re.IGNORECASE)
SEPARATORS = re.compile(r"[\s=,;\"']+")
# Xcode names a workspace's DerivedData folder NAME-<28 letters>; other folders are shared caches.
WORKSPACE_FOLDER = re.compile(r".+-[a-z]{28}")
# Ignored files under a directory of one of these names may be evidence; their worktree is kept.
# Caches a tool writes beside the files are not.
EVIDENCE_NAMES = {"measurements", "evidence"}
CACHE_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".build", ".swiftpm", ".DS_Store"}
DATA_VOLUME = "/System/Volumes/Data"


@dataclass
class Item:
    category: str
    path: str
    status: str
    reason: str
    size: int = 0
    command: list = None
    idle: float = None
    location: str = None  # the directory on disk, when the path is a device's name


@dataclass(frozen=True)
class Process:
    pid: int
    command: str = ""
    cwd: str = ""
    paths: tuple = ()
    args: str = ""


def account_home():
    """The account's home from the password database, so a private HOME joins the same view."""
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def canonical(path):
    """Compare /tmp and /var paths with the /private paths lsof reports."""
    path = os.path.normpath(str(path))
    for alias in ("/tmp", "/var", "/etc"):
        if path == alias or path.startswith(alias + "/"): return "/private" + path
    return path


def within(path, root):
    path, root = canonical(path), canonical(root).rstrip("/")
    return path == root or path.startswith(root + "/")


def human(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB": return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def age(seconds):
    if seconds is None: return "unknown"
    if seconds < 2 * 3600: return f"{seconds / 60:.0f} min"
    if seconds < 2 * 86400: return f"{seconds / 3600:.0f} h"
    return f"{seconds / 86400:.1f} days"


def census(run=subprocess.run):
    """Every process this account can see, with its working directory, open paths and arguments."""
    listing = run(["lsof", "-nP", "-w", "-F", "pcfn"], capture_output=True, text=True, timeout=600).stdout
    found, entry, descriptor = {}, None, None
    for line in listing.splitlines():
        tag, value = line[:1], line[1:]
        if tag == "p": entry = found.setdefault(int(value), {"command": "", "cwd": "", "paths": set()})
        elif entry is None: continue
        elif tag == "c": entry["command"] = value
        elif tag == "f": descriptor = value
        elif tag == "n" and value.startswith("/"):
            if descriptor == "cwd": entry["cwd"] = value
            else: entry["paths"].add(value)
    arguments = {}
    for line in run(["ps", "-Aww", "-o", "pid=,args="], capture_output=True, text=True, timeout=120).stdout.splitlines():
        pid, _, args = line.strip().partition(" ")
        if pid.isdigit(): arguments[int(pid)] = args.strip()
    # Without a census nothing can be shown unused, so fail rather than report candidates.
    if not found or not arguments: raise RuntimeError("could not list processes with lsof and ps")
    own = os.getpid()
    return [Process(pid, entry["command"], entry["cwd"], tuple(sorted(entry["paths"])), arguments.get(pid, ""))
            for pid, entry in found.items() if pid != own] + \
           [Process(pid, args=args) for pid, args in arguments.items() if pid not in found and pid != own]


class Usage:
    """Answers which live process uses a path, from one census of the host."""

    def __init__(self, processes):
        self.by_path = {}
        self.arguments = [(process, process.args.upper()) for process in processes]
        for process in processes:
            uses = [(process.cwd, "working directory")] + [(name, "open file") for name in process.paths]
            uses += [(token, "argument") for token in SEPARATORS.split(process.args) if token.startswith("/")]
            for value, how in uses:
                value = canonical(value) if value else ""
                # Register every ancestor, so a lookup finds any use at or below a path.
                while value not in ("", "/") and value not in self.by_path:
                    self.by_path[value] = (process, how)
                    value = os.path.dirname(value)

    def of(self, path):
        return self.by_path.get(canonical(os.path.realpath(path))) or self.by_path.get(canonical(path))

    def naming(self, text):
        text = text.upper()
        return next((process for process, arguments in self.arguments if text in arguments), None)


def described(use):
    process, how = use
    return f"PID {process.pid} ({process.command or process.args.split(' ')[0] or '?'}) has its {how} inside"


class Sizes:
    """Allocated sizes from du, primed by one pass over each large root."""

    def __init__(self, run=subprocess.run, measure=True):
        self.run, self.measure, self.known, self.unreadable = run, measure, {}, []

    def prime(self, root, depth):
        if not self.measure or not os.path.isdir(root): return
        result = self.run(["du", "-k", "-x", "-d", str(depth), str(root)], capture_output=True, text=True)
        self._read(result)

    def _read(self, result):
        for line in result.stdout.splitlines():
            kilobytes, _, path = line.partition("\t")
            if kilobytes.isdigit(): self.known[canonical(path)] = int(kilobytes) * 1024
        # An iCloud placeholder answers "Resource deadlock avoided" and takes no local space.
        self.unreadable += [line[4:].rsplit(": ", 1)[0] for line in result.stderr.splitlines()
                            if line.startswith("du: ") and not line.endswith("Resource deadlock avoided")]

    def of(self, path):
        if not self.measure: return 0
        key = canonical(path)
        if key not in self.known:
            self._read(self.run(["du", "-skx", str(path)], capture_output=True, text=True))
            self.known.setdefault(key, 0)
        return self.known[key]


@dataclass
class Host:
    """Everything the inventory reads from the machine, so tests can supply it."""
    home: Path
    development: Path
    now: float
    min_idle: float
    processes: list
    simulators: dict = None
    runtimes: dict = None
    default_devices: frozenset = frozenset()
    device_directory: Path = None
    records: dict = field(default_factory=dict)
    temp_roots: list = field(default_factory=list)
    session_scratch: Path = None
    map_roots: list = field(default_factory=list)
    run: object = subprocess.run

    @classmethod
    def current(cls, min_idle, development=None, run=subprocess.run):
        home = account_home()
        devices = home / "Library/Developer/CoreSimulator/Devices"
        temp = [(Path("/private/tmp"), 6)]
        user_temp = run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True).stdout.strip()
        if user_temp: temp.append((Path(os.path.realpath(user_temp)), 2))
        return cls(home=home, development=Path(development or home / "Development"), now=time.time(),
                   min_idle=min_idle, processes=census(run), simulators=_json(run, "list", "-j"),
                   runtimes=_json(run, "runtime", "list", "-j"), default_devices=default_devices(devices),
                   device_directory=devices, records=device_records(), temp_roots=temp,
                   session_scratch=Path(f"/private/tmp/claude-{os.getuid()}"),
                   map_roots=expanded_roots(home, user_temp), run=run)


def _json(run, *arguments):
    try:
        result = run(["xcrun", "simctl", *arguments], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return json.loads(result.stdout) if result.returncode == 0 else None
    except ValueError:
        return None


def default_devices(directory):
    """The devices CoreSimulator made for each runtime, which any session may use."""
    try:
        with open(Path(directory) / "device_set.plist", "rb") as handle:
            defaults = plistlib.load(handle).get("DefaultDevices", {})
    except (OSError, plistlib.InvalidFileException, ValueError):
        return frozenset()
    return frozenset(udid.upper() for types in defaults.values() if isinstance(types, dict)
                     for udid in types.values() if isinstance(udid, str))


def device_records():
    """Every device reservation record's text, or None when a record exists but cannot be read.

    The devices module owns the paths. The account's record is read even under an override, so an
    isolated record never hides a real reservation, and legacy records still count."""
    paths = list(dict.fromkeys([device_record.record_path(), device_record.default_path()]))
    paths += sorted(map(Path, glob.glob(device_record.LEGACY)))
    records = {}
    for path in paths:
        if not path.exists(): continue
        try: records[str(path)] = path.read_text(errors="replace")
        except OSError: records[str(path)] = None
    return records


def expanded_roots(home, user_temp):
    """Directories whose children the map of large directories lists separately."""
    roots = [home, home / "Development", home / "Library", home / "Library/Developer", home / "Library/Caches",
             home / "Library/Application Support", Path("/private/tmp"), Path(f"/private/tmp/claude-{os.getuid()}"),
             Path("/Users"), Path("/Applications")]
    leaves = [Path("/Library"), Path("/opt")] + ([Path(os.path.realpath(user_temp))] if user_temp else [])
    return [(root, None) for root in roots] + [(leaf, "leaf") for leaf in leaves]


def git_environment():
    # A hook's exported GIT_DIR and its relatives would point every command at one repository.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_OPTIONAL_LOCKS"] = "0"  # status must not refresh another session's index
    return environment


def git(run, cwd, *arguments, timeout=300):
    return run(["git", "-C", str(cwd), *arguments], capture_output=True, text=True, timeout=timeout,
               env=git_environment())


def last_activity(path):
    """The newest change to a directory, its top-level entries and, for a worktree, its Git state."""
    path = Path(path)
    paths = [path]
    try: paths += list(path.iterdir())
    except OSError: pass
    try:
        text = (path / ".git").read_text()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip())
            gitdir = gitdir if gitdir.is_absolute() else path / gitdir
            paths += [gitdir / "HEAD", gitdir / "index", gitdir / "logs/HEAD"]
    except OSError: pass
    times = []
    for candidate in paths:
        try: times.append(candidate.lstat().st_mtime)
        except OSError: pass
    return max(times) if times else 0.0


# Linked worktrees

def parse_worktrees(text):
    entries = []
    for line in text.splitlines():
        if line.startswith("worktree "): entries.append({"worktree": line[len("worktree "):]})
        elif entries and line:
            key, _, value = line.partition(" ")
            entries[-1][key] = value
    return entries


def landing_base(run, main):
    """The commit origin/main named when this inventory read it, read once per repository."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main"):
        result = git(run, main, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        if result.returncode == 0 and result.stdout.strip():
            name = git(run, main, "rev-parse", "--abbrev-ref", ref).stdout.strip() or ref
            return result.stdout.strip(), name
    return None, None


def landed(run, main, head, base, name):
    """Whether HEAD's work is in BASE: contained in it, or every commit has an equal patch there."""
    short = f"HEAD {head[:10]}"
    if git(run, main, "merge-base", "--is-ancestor", head, base).returncode == 0:
        return True, f"{short} is in {name} {base[:10]}"
    merges = git(run, main, "rev-list", "--merges", f"{base}..{head}")
    marks = git(run, main, "rev-list", "--cherry-mark", "--right-only", "--no-merges", f"{base}...{head}")
    if merges.returncode or marks.returncode: return False, f"could not compare {short} with {name}"
    if merges.stdout.strip(): return False, f"merge commits on {short} are not in {name} {base[:10]}"
    commits = marks.stdout.split()
    pending = [commit for commit in commits if not commit.startswith("=")]
    if commits and not pending: return True, f"each of the {len(commits)} commits on {short} has an equal patch in {name}"
    return False, f"{len(pending)} commits on {short} are not in {name} {base[:10]}"


def possible_evidence(path):
    parts = Path(path).parts
    if not parts or parts[-1] in CACHE_NAMES or parts[-1].endswith(".pyc"): return False
    return bool(EVIDENCE_NAMES & {part.lower() for part in parts})


def session_root(host, main, path):
    for root in (Path(main) / ".claude/worktrees", Path(main) / ".codex/worktrees", host.home / ".codex/worktrees"):
        if within(path, root) and canonical(path) != canonical(root): return root
    return None


def worktree(host, usage, sizes, main, entry, base, name):
    path = entry["worktree"]
    def item(status, reason, command=None, idle=None):
        return Item("worktree", path, status, reason, sizes.of(path) if os.path.isdir(path) else 0, command, idle)
    if "prunable" in entry or not os.path.isdir(path):
        return item(OWNER, "registered, but its directory is gone; `git worktree prune` forgets every such entry",
                    ["git", "-C", str(main), "worktree", "prune"])
    if "locked" in entry: return item(KEPT, "locked" + (f": {entry['locked']}" if entry["locked"] else ""))
    use = usage.of(path)
    if use: return item(KEPT, "in use: " + described(use))
    # "matching" names each ignored path; "traditional" folds a directory holding only ignored
    # files into one line, which hides whether evidence is inside it.
    status = git(host.run, path, "status", "--porcelain", "--ignored=matching", "--untracked-files=normal")
    if status.returncode: return item(KEPT, "git status failed: " + status.stderr.strip()[:200])
    lines = status.stdout.splitlines()
    changed = [line for line in lines if not line.startswith("!! ")]
    if changed: return item(KEPT, f"dirty: {len(changed)} modified or untracked paths")
    evidence = [line[3:] for line in lines if line.startswith("!! ") and possible_evidence(line[3:])]
    if evidence: return item(KEPT, "ignored files that may be evidence: " + ", ".join(evidence[:3]))
    if not entry.get("HEAD") or not base: return item(KEPT, "no HEAD or no origin/main to compare it with")
    done, why = landed(host.run, main, entry["HEAD"], base, name)
    if not done: return item(KEPT, "unlanded: " + why)
    idle = host.now - last_activity(path)
    if idle < host.min_idle: return item(KEPT, f"clean and landed ({why}), but changed {age(idle)} ago", idle=idle)
    command = ["git", "-C", str(main), "worktree", "remove", path]
    reason = f"clean, unlocked, no process; {why}; idle {age(idle)}"
    if session_root(host, main, path) is None:
        return item(OWNER, reason + "; outside the session worktree directories, so a persistent or shared checkout",
                    command, idle)
    return item(CANDIDATE, reason, command, idle)


def unregistered(host, usage, sizes, mains, registered):
    """Directories in the session worktree directories that no repository has registered."""
    directories = []
    for root in [main / ".claude/worktrees" for main in mains] + [main / ".codex/worktrees" for main in mains]:
        if root.is_dir(): directories += [child for child in root.iterdir() if child.is_dir() and not child.is_symlink()]
    codex = host.home / ".codex/worktrees"
    if codex.is_dir():
        for group in codex.iterdir():
            if group.is_dir() and not group.is_symlink():
                directories += [child for child in group.iterdir() if child.is_dir() and not child.is_symlink()]
    items = []
    for directory in directories:
        key = canonical(os.path.realpath(directory))
        if key in registered or any(within(path, key) for path in registered): continue
        def item(status, reason, command=None):
            return Item("worktree", str(directory), status, reason, sizes.of(directory), command,
                        host.now - last_activity(directory))
        use = usage.of(directory)
        if use:
            items.append(item(KEPT, "not a registered worktree, but in use: " + described(use)))
            continue
        gitdir = None
        try:
            text = (directory / ".git").read_text()
            gitdir = Path(text.split(":", 1)[1].strip()) if text.startswith("gitdir:") else None
        except OSError: pass
        if (directory / ".git").is_dir():
            items.append(item(KEPT, "a separate repository, not a linked worktree"))
        elif gitdir is not None and gitdir.exists():
            items.append(item(KEPT, f"registered with a repository outside {host.development}: {gitdir}"))
        else:
            items.append(item(OWNER, "no repository has registered it, so Git cannot show whether it holds "
                                     "uncommitted work", ["rm", "-rf", "--", str(directory)]))
    return items


def main_checkouts(host):
    if not host.development.is_dir(): return []
    return sorted(path for path in host.development.iterdir() if (path / ".git").is_dir())


def checkouts(host):
    """Every main checkout in the projects directory and every registered worktree on disk."""
    paths = main_checkouts(host)
    for main in list(paths):
        listing = git(host.run, main, "worktree", "list", "--porcelain")
        paths += [Path(entry["worktree"]) for entry in parse_worktrees(listing.stdout)[1:]
                  if os.path.isdir(entry["worktree"])]
    return paths


def encoded(path):
    """Claude Code names a session's scratch directory after its checkout, each other character a hyphen."""
    return re.sub(r"[^A-Za-z0-9-]", "-", str(path))


def worktrees(host, usage, sizes):
    mains = main_checkouts(host)
    items, registered = [], set()
    for main in mains:
        listing = git(host.run, main, "worktree", "list", "--porcelain")
        if listing.returncode:
            items.append(Item("worktree", str(main), KEPT, "git worktree list failed: " + listing.stderr.strip()[:200]))
            continue
        entries = parse_worktrees(listing.stdout)[1:]  # the first is the main worktree
        base, name = landing_base(host.run, main)
        for entry in entries:
            registered.add(canonical(os.path.realpath(entry["worktree"])))
            items.append(worktree(host, usage, sizes, main, entry, base, name))
    return items + unregistered(host, usage, sizes, mains, registered)


# Simulators and runtimes

def disposable_name(name):
    """A disposable device carries a UUID in its unique name; a pool or default device never does."""
    return bool(UUID.search(name))


def last_used(device, directory, now):
    stamp = device.get("lastUsedAt") or device.get("lastBootedAt")
    if stamp:
        try: return now - datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError: pass
    return now - last_activity(directory) if directory and os.path.isdir(directory) else None


def simulators(host, usage, sizes):
    if host.simulators is None:
        return [Item("simulator", "simctl", KEPT, "`xcrun simctl list -j` failed, so no simulator can be shown unowned")]
    unreadable = [path for path, text in host.records.items() if text is None]
    items, listed = [], set()
    for runtime, devices in host.simulators.get("devices", {}).items():
        for device in devices:
            udid, name = device["udid"].upper(), device.get("name", "")
            listed.add(udid)
            data = device.get("dataPath")
            directory = os.path.dirname(data) if data else (str(host.device_directory / udid) if host.device_directory else "")
            size = sizes.of(directory) if directory and os.path.isdir(directory) else \
                int(device.get("dataPathSize") or 0) + int(device.get("logPathSize") or 0)
            idle = last_used(device, directory, host.now)
            label = f"{udid} {name} ({runtime.rsplit('.', 1)[-1]})"
            def item(status, reason, command=None):
                return Item("simulator", label, status, reason, size, command, idle, directory or None)
            command = ["xcrun", "simctl", "delete", udid]
            # A record names a device by UDID or by its name as a JSON string.
            record = next((path for path, text in host.records.items() if text and (udid in text.upper() or
                          (name and json.dumps(name).upper() in text.upper()))), None)
            use = usage.of(directory) if directory else None
            process = usage.naming(udid)
            if device.get("state") != "Shutdown": items.append(item(KEPT, f"{device.get('state')}: a session is using it"))
            elif unreadable: items.append(item(KEPT, "a device record could not be read: " + ", ".join(unreadable)))
            elif record: items.append(item(KEPT, f"named in the device record {record}"))
            elif use: items.append(item(KEPT, "in use: " + described(use)))
            elif process: items.append(item(KEPT, f"named in the arguments of PID {process.pid}"))
            elif disposable_name(name):
                if idle is not None and idle >= host.min_idle:
                    gone = "" if device.get("isAvailable", True) else "; unavailable, its runtime is gone"
                    items.append(item(CANDIDATE, f"a disposable device (unique name) left shut down and unreferenced; "
                                                 f"last used {age(idle)} ago{gone}", command))
                else: items.append(item(KEPT, "a disposable device with no recorded use" if idle is None
                                        else f"a disposable device last used {age(idle)} ago"))
            elif not device.get("isAvailable", True):
                items.append(item(OWNER, f"unavailable ({device.get('availabilityError', 'runtime missing')}); "
                                         "a named device whose use only the owner knows", command))
            elif udid in host.default_devices:
                items.append(item(OWNER, "Xcode's default device for its runtime; any session may use it", command))
            else:
                items.append(item(KEPT, "a named device: a project's reserved pool member or one made by hand; "
                                        "only its owner removes it"))
    if host.device_directory and host.device_directory.is_dir():
        for directory in host.device_directory.iterdir():
            if directory.is_dir() and UUID.fullmatch(directory.name) and directory.name.upper() not in listed:
                use = usage.of(directory)
                items.append(Item("simulator", str(directory), KEPT if use else OWNER,
                                  "in use: " + described(use) if use else "a device directory CoreSimulator no longer lists",
                                  sizes.of(directory), None if use else ["rm", "-rf", "--", str(directory)],
                                  host.now - last_activity(directory)))
    return items


def runtimes(host):
    if host.runtimes is None or host.simulators is None: return []
    used = {}
    for runtime, devices in host.simulators.get("devices", {}).items():
        used[runtime] = used.get(runtime, 0) + len(devices)
    items = []
    for key, image in host.runtimes.items():
        identifier = image.get("runtimeIdentifier", "")
        label = f"{image.get('identifier', key)} {identifier.rsplit('.', 1)[-1]} ({image.get('build', '?')})"
        size, stamp = int(image.get("sizeBytes") or 0), image.get("lastUsedAt")
        if used.get(identifier):
            items.append(Item("runtime", label, KEPT, f"{used[identifier]} devices use it", size))
        elif image.get("deletable") is False:
            items.append(Item("runtime", label, KEPT, "not deletable: it came with Xcode", size))
        else:
            items.append(Item("runtime", label, OWNER, f"no device uses it; last used {stamp or 'never'}; a lane may "
                              "create its devices on it next", size,
                              ["xcrun", "simctl", "runtime", "delete", image.get("identifier", key)]))
    return items


# Build caches and results

def cache_item(host, usage, sizes, category, path, reason):
    idle = host.now - last_activity(path)
    use = usage.of(path)
    if use: return Item(category, str(path), KEPT, "in use: " + described(use), sizes.of(path), None, idle)
    if idle < host.min_idle:
        return Item(category, str(path), KEPT, f"{reason}, but changed {age(idle)} ago", sizes.of(path), None, idle)
    return Item(category, str(path), CANDIDATE, f"{reason}; no process; idle {age(idle)}", sizes.of(path),
                ["rm", "-rf", "--", str(path)], idle)


def derived_data(host, usage, sizes):
    root = host.home / "Library/Developer/Xcode/DerivedData"
    if not root.is_dir(): return []
    items = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink(): continue
        if not WORKSPACE_FOLDER.fullmatch(child.name):
            items.append(Item("derived-data", str(child), KEPT, "shared by every Xcode build", sizes.of(child)))
            continue
        try:
            with open(child / "info.plist", "rb") as handle:
                workspace = plistlib.load(handle).get("WorkspacePath")
        except (OSError, plistlib.InvalidFileException, ValueError):
            workspace = None
        if not workspace:
            use = usage.of(child)
            held = ", ".join(sorted(entry.name for entry in child.iterdir())[:5]) or "nothing"
            items.append(Item("derived-data", str(child), KEPT if use else OWNER,
                              "in use: " + described(use) if use else f"records no workspace; holds {held}",
                              sizes.of(child), None if use else ["rm", "-rf", "--", str(child)],
                              host.now - last_activity(child)))
        elif os.path.exists(workspace):
            items.append(Item("derived-data", str(child), KEPT, f"its workspace {workspace} exists", sizes.of(child)))
        else:
            items.append(cache_item(host, usage, sizes, "derived-data", child, f"its workspace {workspace} is gone"))
    return items


def swiftpm_cache(host, usage, sizes):
    root = host.home / "Library/Caches/org.swift.swiftpm"
    items = []
    for kind, what in (("repositories", "a cached clone"), ("artifacts", "a cached binary artifact")):
        directory = root / kind
        if directory.is_dir():
            items += [cache_item(host, usage, sizes, "swiftpm-cache", child, what + " SwiftPM fetches again when needed")
                      for child in sorted(directory.iterdir()) if child.is_dir() and not child.is_symlink()]
    return items


def archives(host, sizes):
    root = host.home / "Library/Developer/Xcode/Archives"
    return [Item("archive", str(archive), OWNER, "an archived build; its dSYMs symbolicate that build's crash reports",
                 sizes.of(archive), ["rm", "-rf", "--", str(archive)], host.now - last_activity(archive))
            for archive in sorted(root.glob("*/*.xcarchive"))] if root.is_dir() else []


def shape(names):
    if "workspace-state.json" in names: return "SwiftPM scratch"
    if "Build" in names and names & {"info.plist", "Logs", "SourcePackages", "Index.noindex", "ModuleCache.noindex"}:
        return "Xcode derived data"
    return None


def owner_record(directory):
    """The PID and start time a results directory records for its run, if it records one."""
    try: pid, _, started = (Path(directory) / "owner").read_text().strip().partition(" ")
    except (OSError, UnicodeDecodeError): return None
    return (int(pid), started.strip()) if pid.isdigit() else None


def run_is_live(run, pid, started):
    current = " ".join(run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True).stdout.split())
    # A reused PID has another start time. A record without one keeps a running PID's run live.
    return bool(current) and (not started or current == " ".join(started.split()))


def live_session(host, sessions, path):
    """Why a path in a Claude Code session's scratch may still be that session's, if it may."""
    if not host.session_scratch or not within(path, host.session_scratch): return None
    relative = os.path.relpath(canonical(path), canonical(host.session_scratch)).split(os.sep)
    name = relative[0] if relative and relative[0] != "." else ""
    if name in sessions: return sessions[name]
    # A session whose worktree was removed can still be running in its old directory.
    for process in host.processes:
        cwd = encoded(process.cwd) if process.cwd else ""
        if name and (cwd == name or cwd.startswith(name + "-")):
            return f"whose PID {process.pid} ({process.command}) still works in its checkout"
    return None


def temp_items(host, usage, sizes):
    """Scratch builds and results found under the temporary roots, outside every checkout."""
    found = []
    def walk(directory, depth):
        try: entries = list(os.scandir(directory))
        except OSError: return
        names = {entry.name for entry in entries}
        kind = shape(names)
        if ".git" in names: pass  # a checkout: the worktree rules decide about it
        elif kind: found.append(("scratch", directory, kind))
        elif "owner" in names and owner_record(directory): found.append(("results", directory, "record"))
        elif depth > 0:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False): continue
                if entry.name.endswith(".xcresult"): found.append(("results", entry.path, "bundle"))
                else: walk(entry.path, depth - 1)
    for root, depth in host.temp_roots:
        walk(str(root), depth)
    sessions = {encoded(checkout): f"whose checkout {checkout} still exists"
                for checkout in checkouts(host)} if host.session_scratch and found else {}
    items = []
    for category, path, kind in found:
        session = live_session(host, sessions, path)
        if category == "scratch" and session:
            items.append(Item("scratch", path, KEPT, f"{kind} in the scratch of a session {session}",
                              sizes.of(path), None, host.now - last_activity(path)))
        elif category == "scratch":
            items.append(cache_item(host, usage, sizes, "scratch", path, f"{kind} outside every checkout"))
        if category == "scratch": continue
        use = usage.of(path)
        record = owner_record(path) if kind == "record" else None
        idle = host.now - last_activity(path)
        if use: items.append(Item("results", path, KEPT, "in use: " + described(use), sizes.of(path), None, idle))
        elif record and run_is_live(host.run, *record):
            items.append(Item("results", path, KEPT, f"its run, PID {record[0]}, is still in progress", sizes.of(path), None, idle))
        else:
            what = "a finished run's results directory; its project prunes these by count" if record else "a test result bundle"
            items.append(Item("results", path, OWNER, f"{what}; keep it while it is worth reading", sizes.of(path),
                              ["rm", "-rf", "--", path], idle))
    return items


def large_directories(host, sizes, items, limit=25):
    """The largest directories besides the items above, from the primed sizes. Never candidates."""
    expanded = {canonical(root) for root, kind in host.map_roots if kind is None}
    leaves = []
    for root, kind in host.map_roots:
        if kind == "leaf": leaves.append(str(root))
        elif os.path.isdir(root):
            try: leaves += [str(child) for child in Path(root).iterdir() if child.is_dir() and not child.is_symlink()
                            and canonical(child) not in expanded]
            except OSError: pass
    measured, entries = 0, []
    for leaf in leaves:
        size = sizes.known.get(canonical(leaf))
        if size is None: continue
        measured += size
        inner = sum(item.size for item in items if item.category != "runtime" and within(item.location or item.path, leaf))
        note = "another account's home" if within(leaf, "/Users") and not within(leaf, host.home) else ""
        if (Path(leaf) / ".git").is_dir(): note = "a project's main checkout, without the worktrees above"
        entries.append(Item("other", leaf, KEPT, note or "reported for the owner", max(size - inner, 0)))
    entries.sort(key=lambda item: -item.size)
    return entries[:limit], measured


def inventory(host, sizes, categories=None):
    usage = Usage(host.processes)
    wanted = set(categories or CATEGORIES)
    items = []
    if "worktree" in wanted: items += worktrees(host, usage, sizes)
    if "simulator" in wanted: items += simulators(host, usage, sizes)
    if "runtime" in wanted: items += runtimes(host)
    if "derived-data" in wanted: items += derived_data(host, usage, sizes)
    if "swiftpm-cache" in wanted: items += swiftpm_cache(host, usage, sizes)
    if "archive" in wanted: items += archives(host, sizes)
    if wanted & {"scratch", "results"}: items += [item for item in temp_items(host, usage, sizes) if item.category in wanted]
    return items


# Reporting

def report(items, others, volume, measured, unreadable, min_size, out=print):
    if volume:
        total, used, free = volume
        out(f"Data volume {DATA_VOLUME}: {human(used)} used of {human(total)}, {human(free)} free.")
    out("This inventory changed nothing. Sizes are allocated sizes from du; APFS clones share blocks, "
        "so removing one can free less.\n")
    for category, title in CATEGORIES.items():
        group = sorted((item for item in (others if category == "other" else items) if item.category == category),
                       key=lambda item: (STATUS_ORDER[item.status], -item.size))
        if not group: continue
        out(title)
        hidden = {}
        for item in group:
            if item.size < min_size and category != "other":
                count, size = hidden.get(item.status, (0, 0))
                hidden[item.status] = (count + 1, size + item.size)
                continue
            out(f"  {item.status:9} {human(item.size):>10}  {item.path}")
            out(f"            {item.reason}")
            if item.command: out(f"            $ {shlex.join(item.command)}")
        for status, (count, size) in hidden.items():
            out(f"  {status:9} {human(size):>10}  and {count} smaller items")
        out("")
    if volume and measured is None:
        out("Run with --map to list the largest other directories and account for the rest of the volume.")
    elif volume:
        missing = volume[1] - measured
        out(f"Measured {human(measured)} of the {human(volume[1])} used. The other {human(max(missing, 0))} is in "
            "places this account cannot read or that were not scanned: folders macOS privacy protection "
            "hides from the shell (such as ~/.Trash, ~/Library/Mail and Messages), other accounts' private "
            "folders, system data and files deleted while still open.")
    if unreadable:
        roots = {}
        for path in unreadable:
            parts = Path(path).parts
            roots[str(Path(*parts[:5]))] = roots.get(str(Path(*parts[:5])), 0) + 1
        top = sorted(roots.items(), key=lambda pair: -pair[1])[:8]
        out("Unreadable during measurement: " + "; ".join(f"{root} ({count})" for root, count in top))
    for status, label in ((CANDIDATE, "Candidates"), (OWNER, "Owner decisions"), (KEPT, "Kept")):
        chosen = [item for item in items if item.status == status]
        out(f"{label}: {len(chosen)} items, {human(sum(item.size for item in chosen))}.")


# Removal

def ledger_path(home):
    return Path(home) / "Library/Application Support/vocaro-engineering/disk-reclaimed.jsonl"


def outside_checkouts(path):
    """A removal target must be an absolute path, reached through no link, below no working tree."""
    path = Path(path)
    if not path.is_absolute() or canonical(os.path.realpath(path)) != canonical(path): return False
    return not any((ancestor / ".git").exists() for ancestor in [path, *path.parents])


def delete(items, fresh, ledger, ask=input, out=print, run=subprocess.run, terminal=None):
    """Remove candidates category by category, after confirmation and a fresh check of each."""
    if not (sys.stdin.isatty() if terminal is None else terminal):
        raise RuntimeError("--delete asks for confirmation on a terminal; run it there")
    removed = 0
    for category, title in CATEGORIES.items():
        group = [item for item in items if item.category == category and item.status == CANDIDATE]
        if not group: continue
        answer = ask(f"Remove {len(group)} {title.lower()} candidates, {human(sum(item.size for item in group))}? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            out(f"Kept every {title.lower()} candidate.")
            continue
        current = {item.path: item for item in fresh(category)}
        for item in group:
            now = current.get(item.path)
            entry = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(), "category": category,
                     "path": item.path, "size": item.size, "reason": item.reason, "command": item.command}
            if now is None or now.status != CANDIDATE or now.command != item.command:
                entry["outcome"] = "skipped: " + (now.reason if now else "no longer present")
            elif item.command[0] == "rm" and not outside_checkouts(item.command[-1]):
                entry["outcome"] = "skipped: inside a repository's working tree or behind a link"
            else:
                result = run(item.command, capture_output=True, text=True, timeout=3600, env=git_environment())
                entry["outcome"] = "removed" if result.returncode == 0 else f"failed ({result.returncode}): {result.stderr.strip()[:300]}"
                removed += result.returncode == 0
            out(f"{entry['outcome']}: {item.path}")
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with open(ledger, "a") as handle: handle.write(json.dumps(entry) + "\n")
    out(f"Removed {removed} items; the record of every decision is in {ledger}.")
    return removed


def add_arguments(parser):
    parser.add_argument("--delete", action="store_true", help="remove candidates after confirming each category")
    parser.add_argument("--json", action="store_true", help="print the items as JSON")
    parser.add_argument("--min-idle-hours", type=float, default=24.0,
                        help="how long a candidate must have been unchanged (default 24)")
    parser.add_argument("--min-size-mb", type=float, default=100.0, help="list smaller items only as totals")
    parser.add_argument("--development", type=Path, help="directory holding the projects (default ~/Development)")
    parser.add_argument("--map", action="store_true",
                        help="also scan the whole home directory, /private/tmp and /Applications for the largest "
                             "other directories and an account of the volume (several minutes)")


def prime_items(host, sizes):
    """One du pass over each folder that holds many small items; everything else is measured alone."""
    for root, depth in ((host.home / "Library/Developer/Xcode/DerivedData", 1), (host.device_directory, 1),
                        (host.home / "Library/Caches/org.swift.swiftpm", 2)):
        if root: sizes.prime(root, depth)


def prime_map(host, sizes):
    """One du pass over the home directory and the other large roots, for the map of the volume."""
    for root, depth in ((host.home, 5), (Path("/private/tmp"), 5), (Path("/Applications"), 1)):
        sizes.prime(root, depth)
    for root, kind in host.map_roots:
        if kind == "leaf": sizes.prime(root, 1)
    if Path("/Users").is_dir():
        for other in Path("/Users").iterdir():
            if other.is_dir() and not within(other, host.home): sizes.prime(other, 0)


def execute(args, run=subprocess.run, out=print):
    def collect(categories=None, measure=True):
        host = Host.current(args.min_idle_hours * 3600, args.development, run)
        sizes = Sizes(run, measure)
        if measure and args.map:
            print("Measuring sizes; --map reads the whole home directory and can take several minutes.", file=sys.stderr)
            prime_map(host, sizes)
        elif measure:
            print("Measuring the items listed; --map also maps the rest of the volume.", file=sys.stderr)
            prime_items(host, sizes)
        return host, sizes, inventory(host, sizes, categories)
    host, sizes, items = collect()
    others, measured = large_directories(host, sizes, items) if args.map else ([], None)
    if measured is not None: measured += sum(item.size for item in items if item.category == "runtime")
    try:
        usage = shutil.disk_usage(DATA_VOLUME)
        volume = (usage.total, usage.used, usage.free)
    except OSError:
        volume = None
    if args.json:
        out(json.dumps({"volume": volume, "measured": measured, "items": [asdict(item) for item in items + others]}, indent=2))
    else:
        report(items, others, volume, measured, sizes.unreadable, args.min_size_mb * 1024 * 1024, out)
    if args.delete:
        delete(items, lambda category: collect([category], measure=False)[2], ledger_path(host.home), out=out, run=run)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="eng disk", description=__doc__.split("\n")[0])
    add_arguments(parser)
    try:
        return execute(parser.parse_args(argv))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"eng disk: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
