"""Run a lane or an admitted command on the build host: a second Mac reached over SSH.

Nothing here takes a slot on this host. The exact commit, and the toolkit commit that runs it,
go to bare repositories on the build host by git over SSH, never through GitHub. build_host.py,
sent along and run there by the host's own Python, checks them out in a persistent checkout,
so builds stay warm, and runs `eng run` or `eng admit` under the build host's own heavy-work
admission: that host's queue, not a private pool beside this one. The log and the result come
back to this checkout's .build/engineering/remote. A whole lane's result is also kept by commit
in the repository's Git directory, where every worktree of the repository can find it.

`eng run` sends a lane marked buildHost here first: when the build host refuses it before
anything runs, because its queue or every checkout is busy or it cannot be reached, the lane
runs on this Mac instead.
"""
import json
import os
from pathlib import Path
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time

from . import build_host, processes
from .config import TOOLKIT_ROOT
from .resources import BUSY

# The SSH destination when neither --host nor VOCARO_BUILD_HOST names one: an alias the owner
# defines in ~/.ssh/config, so no machine's name is written here.
DEFAULT_HOST = "build-host"
# The build host's directory for repositories and checkouts, relative to its home.
ROOT = "Development/build-host"
# Persistent checkouts per project on the build host; more wait for one to come free.
CHECKOUTS = 4
SSH = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30",
       "-o", "ServerAliveCountMax=4"]
REF = "refs/vocaro/build-host/"
# Seconds a stopped run has to end on the build host before the connection is closed.
STOP_WAIT = 120
# What a Git hook exports for its own repository must not reach another.
GIT_LOCATION = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_PREFIX"}


class Unavailable(RuntimeError):
    """The build host did not take the work, and nothing of it ran there."""


def configured():
    """The build host to send buildHost lanes to first, or None for this Mac only.

    VOCARO_BUILD_HOST names it, and `none` turns it off. Otherwise it is the ssh alias, when
    ~/.ssh/config defines one: `ssh -G` resolves an undefined alias to its own name.
    """
    named = os.environ.get("VOCARO_BUILD_HOST")
    if named is not None:
        return None if named.strip().lower() in {"", "none", "off"} else named
    try:
        resolved = subprocess.run(["ssh", "-G", DEFAULT_HOST], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    names = [line.split(None, 1)[1] for line in resolved.stdout.splitlines() if line.startswith("hostname ")]
    return DEFAULT_HOST if resolved.returncode == 0 and names and names[0] != DEFAULT_HOST else None


def environment():
    return {key: value for key, value in os.environ.items() if key not in GIT_LOCATION}


def git(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True,
                            env=environment(), timeout=120)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(arguments)} in {root} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def committed(root, untracked):
    """HEAD of a checkout with nothing uncommitted: the build host runs commits, not working trees."""
    status = git(root, "status", "--porcelain", f"--untracked-files={'normal' if untracked else 'no'}")
    if status:
        raise Unavailable(f"{root} has changes the build host would not run; commit them first:\n{status}")
    return git(root, "rev-parse", "HEAD")


def common_directory(root):
    return Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))


def checkout_name(root):
    """The main checkout's directory name, from a linked worktree too."""
    common = common_directory(root)
    return common.parent.name if common.name == ".git" else Path(root).resolve().name


def origin(root):
    """The toolkit's public origin for the build host's policy refresh, which needs no GitHub key."""
    try: url = git(root, "config", "--get", "remote.origin.url")
    except RuntimeError: return None
    return "https://github.com/" + url[len("git@github.com:"):] if url.startswith("git@github.com:") else url


def developer_directory():
    selected = os.environ.get("DEVELOPER_DIR") or build_host.output(["xcode-select", "-p"])
    return selected if selected and Path(selected).is_dir() else None


def login(script):
    """Have the build host's login shell run script, so its PATH is Terminal's, Homebrew's included."""
    return f'exec "$SHELL" -l -c {shlex.quote(script)}'


def ssh(host, script, **options):
    return subprocess.run([*SSH, host, login(script)], env=environment(), **options)


def send(root, host, repository, commit):
    """Push one commit by name to a bare repository on the build host, without the push hooks:
    this is no publication, and a pre-push hook would run the gates this offloads."""
    variables = {**environment(), "GIT_SSH_COMMAND": shlex.join(SSH)}
    result = subprocess.run(["git", "-C", str(root), "push", "--no-verify", "--quiet", "--receive-pack=git receive-pack",
                             f"{host}:{repository}", f"{commit}:{REF}{commit}"], env=variables)
    if result.returncode:
        raise Unavailable(f"Could not send {commit} to {host}:{repository} (git push exited {result.returncode})")


def store(root):
    return common_directory(root) / "vocaro-engineering/remote"


def passed(root, lane, revision="HEAD"):
    """The receipt of a passing build-host run of the whole lane at exactly revision's commit, or None."""
    commit = git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    try:
        receipt = json.loads((store(root) / commit / f"{lane}.json").read_text())
    except (OSError, ValueError):
        return None
    result = receipt.get("result", {})
    whole = receipt.get("commit") == commit and receipt.get("lane") == lane and not receipt.get("arguments")
    return receipt if whole and result.get("exitStatus") == 0 and not result.get("stopped") else None


def write(stream, data):
    try: stream.buffer.write(data)
    except AttributeError: stream.write(data.decode(errors="replace"))
    stream.flush()


def describe(identity):
    xcode = (identity.get("xcode") or "no Xcode").splitlines()
    return (f"{identity.get('name')} ({identity.get('model')}, macOS {identity.get('macOS')} "
            f"({identity.get('build')}), {', '.join(xcode)})")


def execute(root, config, host, work, *, lane=None, arguments=(), expect=None, decline=False):
    """Run eng's work on the build host and return its exit status, with the log and receipt kept here.

    work is the build host's eng arguments: run [--expect N] LANE [-- ARGUMENTS] or
    admit [--exclusive] -- COMMAND. With decline, the build host refuses work it cannot start now
    rather than waiting for it, and Unavailable says why.
    """
    toolkit = Path(TOOLKIT_ROOT).resolve()
    try:
        commit = committed(root, untracked=True)
        directory = checkout_name(root)
        kept = store(root) / commit
        kit = None
        project = {"directory": directory, "repository": f"repositories/{directory}.git", "commit": commit,
                   "ref": f"{REF}{commit}"}
        if toolkit == Path(root).resolve():
            project["origin"] = origin(root)
        else:
            kit_commit = committed(toolkit, untracked=False)
            kit_directory = checkout_name(toolkit)
            kit = {"directory": kit_directory, "repository": f"repositories/{kit_directory}.git",
                   "commit": kit_commit, "ref": f"{REF}{kit_commit}", "origin": origin(toolkit)}
    except RuntimeError as error:  # Git cannot name a commit to send, so nothing is sent.
        raise Unavailable(str(error)) from error
    developer = developer_directory()
    local = build_host.identity(developer)
    name = lane if lane is not None else "admit"
    plan = {"root": ROOT, "checkouts": CHECKOUTS, "project": project, "toolkit": kit, "work": work,
            "decline": decline, "busy": BUSY,
            "provision": "provision" in config.get("lanes", {}) and lane != "provision",
            "developerDir": developer, "xcode": local["xcode"],
            "log": f".build/engineering/{lane}/run.log" if lane is not None else None,
            "receipt": f".build/engineering/{name}/source.json"}

    repositories = [f"{ROOT}/{part['repository']}" for part in (project, kit) if part is not None]
    prepare = " && ".join([f"mkdir -p {shlex.quote(ROOT + '/repositories')}", *(
        f"{{ [ -d {shlex.quote(path)} ] || git init --bare --quiet {shlex.quote(path)}; }}" for path in repositories)])
    print(f"remote: sending {commit[:12]} to {host}", file=sys.stderr, flush=True)
    if ssh(host, prepare, stdin=subprocess.DEVNULL).returncode:
        raise Unavailable(f"Could not reach {host} or prepare {ROOT} there; check `ssh {host} true`")
    send(root, host, repositories[0], commit)
    if kit is not None: send(toolkit, host, repositories[1], kit["commit"])
    if processes.requested() is not None:
        raise processes.Interrupted(processes.requested(), "before the build host started the run")

    results = Path(root) / ".build/engineering/remote" / name
    # Results are staged, so a refusal leaves the previous run's whole.
    staging = results.with_name(f".{name}.{os.getpid()}")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    started = time.time()
    source = Path(build_host.__file__).read_text()
    command = [*SSH, host, login(shlex.join(["python3", "-c", source, json.dumps(plan)]))]
    lines, result, stopping = queue.Queue(), None, None
    with (staging / "run.log").open("wb") as log, (staging / "output.log").open("wb") as output:
        channel = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env=environment())
        def relay():
            for line in iter(channel.stdout.readline, b""): lines.put(line)
            lines.put(None)
        threading.Thread(target=relay, daemon=True).start()
        while True:
            if processes.requested() is not None and stopping is None:
                stopping = time.monotonic()
                print(f"remote: stop requested; asking {host} to stop the run", file=sys.stderr, flush=True)
                # The end of the build host's standard input is its stop.
                try: channel.stdin.close()
                except OSError: pass
            if stopping is not None and time.monotonic() - stopping > STOP_WAIT and channel.poll() is None:
                print(f"remote: {host} did not finish stopping in {STOP_WAIT}s; closing the connection",
                      file=sys.stderr, flush=True)
                channel.terminate()
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None: break
            kind, data = line[:2], line[2:]
            if kind == b"L ":
                log.write(data)
            elif kind == b"R ":
                result = json.loads(data)
            else:
                data = data if kind == b"O " else line
                output.write(data)
                write(sys.stdout, data)
        channel.wait()
    if result is not None and result.get("refused"):
        shutil.rmtree(staging, ignore_errors=True)
        raise Unavailable(f"{host} did not take it: {result['refused']}")
    shutil.rmtree(results, ignore_errors=True)
    staging.rename(results)
    if result is None:
        raise RuntimeError(f"No result from {host} (ssh exited {channel.returncode}); the run is unmeasured. "
                           f"Its output is in {results / 'output.log'}")
    receipt = {"host": host, "commit": commit, "toolkit": kit["commit"] if kit else commit, "lane": lane,
               "arguments": list(arguments), "expect": expect, "work": work, "local": local, "result": result,
               "dispatched": started}
    (results / "source.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if lane is not None and not arguments and expect is None:
        kept.mkdir(parents=True, exist_ok=True)
        (kept / f"{lane}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if result.get("error"):
        raise RuntimeError(f"{host}: {result['error']}")
    status = result["exitStatus"]
    remote = result["host"]
    print(f"remote: {name} at {commit[:12]} on {describe(remote)} in {result.get('checkout')}: "
          f"{'stopped' if result['stopped'] else f'exit {status}'}; results in {results}", file=sys.stderr, flush=True)
    if (remote.get("macOS"), remote.get("build")) != (local.get("macOS"), local.get("build")):
        print(f"remote: the build host runs macOS {remote.get('macOS')} ({remote.get('build')}) and this Mac "
              f"{local.get('macOS')} ({local.get('build')}): the result qualifies the build host's platform",
              file=sys.stderr, flush=True)
    if status is None: return 1
    # A command a signal ended has a negative status; a shell reports it as 128 plus the signal.
    return 128 - status if status < 0 else status


def main(root, config, args):
    if args.operation == "passed":
        receipt = passed(root, args.lane, args.commit)
        if receipt is None:
            print(f"No passing build-host run of the whole {args.lane} lane at {args.commit}")
            return 1
        print(f"{args.lane} passed at {receipt['commit']} on {describe(receipt['result']['host'])}")
        return 0
    host = args.host or os.environ.get("VOCARO_BUILD_HOST") or DEFAULT_HOST
    if args.operation == "run":
        lane = config.get("lanes", {}).get(args.lane)
        if lane is None: raise ValueError(f"No configured lane: {args.lane}")
        if lane.get("foreground"): raise ValueError(f"{args.lane} takes the screen; foreground lanes run only here")
        if args.expect is not None and args.expect < 1: raise ValueError("--expect needs at least 1 test")
        extra = args.passed or []
        work = ["run", "--here", *(["--expect", str(args.expect)] if args.expect else []), args.lane,
                *(["--", *extra] if extra else [])]
        with processes.forwarding_signals():
            return execute(root, config, host, work, lane=args.lane, arguments=extra, expect=args.expect)
    # Without a leading --, argparse collected the command, and a later -- belongs to it.
    command = args.command + ([] if args.passed is None else ["--", *args.passed]) if args.command else args.passed
    if not command: raise ValueError("Name the command: eng remote admit [--exclusive] -- COMMAND")
    with processes.forwarding_signals():
        return execute(root, config, host, ["admit", *(["--exclusive"] if args.exclusive else []), "--", *command])


def first(root, config, lane, arguments, expect):
    """Run a buildHost lane on the build host if it takes it now and return its status, or None
    after saying why it runs on this Mac instead."""
    host = configured()
    if host is None: return None
    work = ["run", "--here", "--if-free", *(["--expect", str(expect)] if expect else []), lane,
            *(["--", *arguments] if arguments else [])]
    try:
        with processes.forwarding_signals():
            return execute(root, config, host, work, lane=lane, arguments=arguments, expect=expect, decline=True)
    except Unavailable as reason:
        print(f"eng: running {lane} on this Mac: {reason}", file=sys.stderr, flush=True)
        return None
