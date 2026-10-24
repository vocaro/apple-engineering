"""Independent work side by side: a lane group's lanes, and a unittest suite's modules in processes
of their own. guides/parallel-tests.md says when each is safe and how to bound it.

A lane group runs inside the one admission its own lane took, as nested work does, so its lanes
take no slot of their own. Each lane writes its own log and keeps its own outcome; the group
fails when any lane failed, and is otherwise unmeasured when any lane was.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unittest

from . import evidence, processes

# Lines of a failed lane's log printed under its result.
TAIL = 40
# Processes `eng unittest` runs at a time unless --jobs says otherwise (guides/parallel-tests.md).
DEFAULT_JOBS = 4
# unittest's own exit status for a run that found no tests (Python 3.12 and later).
NO_TESTS = 5


def outcome(status):
    return "PASS" if status == 0 else "UNMEASURED" if status == evidence.UNMEASURED else "FAIL"


def combined(statuses):
    """1 when any status failed, else UNMEASURED when any was unmeasured, else 0."""
    if any(status not in (0, evidence.UNMEASURED) for status in statuses): return 1
    return evidence.UNMEASURED if evidence.UNMEASURED in statuses else 0


def lanes(root, members, directory, jobs, judge, receipt, on_stop=None):
    """Run members, (name, lane) pairs, jobs at a time, each with its log at directory/NAME.log,
    and return the combined status. judge(lane, status, log) is a lane's status from its command's
    and its log, raising ValueError for a run that executed too few tests.

    Every lane runs to its own end, however the others end. A stop reaches every running lane and
    starts none of the rest; once all have ended the stop is raised, or the uncertainty of a lane
    whose processes were not seen to end, which keeps the admission's guard.
    """
    directory.mkdir(parents=True, exist_ok=True)
    results, lock, started = {}, threading.Lock(), time.monotonic()

    def say(*lines):
        with lock: print(*lines, sep="\n", flush=True)

    def one(name, lane):
        log = directory / f"{name}.log"
        say(f"RUN {name}")
        began = time.monotonic()
        try:
            status = processes.run(lane["command"], cwd=root, log_path=log, timeout=lane.get("timeout"),
                                   on_stop=on_stop)
            status = judge(lane, status, log.read_text(errors="replace"))
        except processes.TimedOut as error:
            # A lane's timeout is its backstop, so a run a busy host slowed past it is unmeasured.
            status, detail = evidence.UNMEASURED, str(error)
        except processes.NotStarted as error:
            status, detail = 2, str(error)
        except ValueError as error:
            status, detail = 2, str(error)
        else:
            detail = None
        seconds = round(time.monotonic() - began)
        results[name] = {"status": status, "seconds": seconds, "log": str(log)}
        lines = [f"{outcome(status)} {name} ({seconds}s, status {status}): {log}"]
        if detail: lines.append(f"    {detail}")
        if outcome(status) != "PASS":
            lines += ["    " + line for line in log.read_text(errors="replace").splitlines()[-TAIL:]] if log.exists() else []
        say(*lines)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(one, name, lane) for name, lane in members]
    failures = [future.exception() for future in futures if future.exception() is not None]
    receipt["lanes"] = results
    if failures:
        uncertain = [error for error in failures if not isinstance(error, processes.Interrupted)]
        raise uncertain[0] if uncertain else failures[0]
    status = combined([results[name]["status"] for name, _lane in members])
    width = max(len(name) for name, _lane in members)
    say(f"Lane times (wall-clock {round(time.monotonic() - started)}s, {jobs} at a time):",
        *(f"  {name:<{width}}  {results[name]['seconds']:>6}s  {outcome(results[name]['status'])}"
          for name, _lane in members), outcome(status))
    return status


def flattened(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite): yield from flattened(test)
        else: yield test


def shards(suite, split):
    """{shard name: [test ids]}, in discovery order. A shard is a module, class or test, as split
    says. Tests whose class or module sets serial_group share one shard, so they run one after
    another in one process. A module that failed to import is a shard of its own, which reports
    the import error when it runs."""
    found = {}
    for test in flattened(suite):
        cls = type(test)
        module = sys.modules.get(cls.__module__)
        if cls.__module__ == "unittest.loader":
            # A _FailedTest's name is the module or package that failed to load.
            name = test.id().rsplit(".", 1)[-1]
            found.setdefault(name, []).append(name)
            continue
        group = getattr(module, "serial_group", None) if split == "module" else \
            getattr(cls, "serial_group", getattr(module, "serial_group", None))
        unit = {"module": cls.__module__, "class": f"{cls.__module__}.{cls.__qualname__}", "test": test.id()}[split]
        found.setdefault(f"group:{group}" if group else unit, []).append(test.id())
    return found


RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
RESULT = re.compile(r"^(OK|FAILED)\b.*$", re.M)


def run_shard(name, tests, top, verbose):
    command = [sys.executable, "-m", "unittest", *(["-v"] if verbose else []), *tests]
    began = time.monotonic()
    finished = subprocess.run(command, cwd=top, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              errors="replace")
    output = finished.stdout
    summary = RESULT.search(output)
    return {"name": name, "status": finished.returncode, "output": output,
            "ran": sum(int(count) for count in RAN.findall(output)),
            "result": summary.group(0) if summary else "no result",
            "seconds": time.monotonic() - began}


def unittest_main(argv):
    parser = argparse.ArgumentParser(prog="eng unittest", description="Discover a unittest suite as `python3 -m "
        "unittest discover` does, and run its modules in processes of their own, JOBS at a time.")
    parser.add_argument("-s", "--start-directory", default=".")
    parser.add_argument("-p", "--pattern", default="test*.py")
    parser.add_argument("-t", "--top-level-directory")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS,
                        help=f"processes at a time (default {DEFAULT_JOBS}); 1 runs them one after another")
    parser.add_argument("--split", choices=["module", "class", "test"], default="module",
                        help="what one process runs (default: one module)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.jobs < 1: parser.error("--jobs needs at least 1")
    start = Path(args.start_directory).resolve()
    top = Path(args.top_level_directory).resolve() if args.top_level_directory else start
    # Discovery imports every module here, as unittest's own would, and each shard imports its own again.
    sys.path.insert(0, str(top))
    loader = unittest.TestLoader()
    found = shards(loader.discover(str(start), args.pattern, str(top)), args.split)
    if not found:
        print(f"eng unittest: no tests found in {start} matching {args.pattern}", file=sys.stderr)
        return NO_TESTS
    expected = {name: len(tests) for name, tests in found.items()}
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_shard, name, tests, top, args.verbose) for name, tests in found.items()]
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
            # Each shard's own output, whole and in discovery order, under one line that names it.
            print(f"== {result['name']}: {result['result']} ({result['ran']} tests, {result['seconds']:.1f}s)",
                  result["output"].rstrip("\n"), sep="\n", flush=True)
    failed = []
    for result in results:
        if result["status"] != 0: failed.append(f"{result['name']} ({result['result']}, status {result['status']})")
        elif result["ran"] != expected[result["name"]]:
            # A shard that ran other than the tests discovery found for it did not run what it was given.
            failed.append(f"{result['name']} (ran {result['ran']} of {expected[result['name']]} tests)")
    total = sum(result["ran"] for result in results)
    # Not "Ran N tests": the shards' own lines already count every test once.
    print(f"eng unittest: {total} tests in {len(results)} processes, {args.jobs} at a time, "
          f"{time.monotonic() - began:.1f}s: " + (f"FAILED: {', '.join(failed)}" if failed else "OK"), flush=True)
    return 1 if failed else 0
