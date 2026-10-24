"""Source identities, positive test counts, and path-safe evidence receipts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# XCTest prints each suite's total on the line after its result. swift test and xcodebuild run
# each bundle under its own top suite, All tests, or Selected tests when filtered. A total
# includes the tests it skipped.
SUITE_TOTAL = re.compile(
    r"^Test Suite '([^'\n]*)' (?:passed|failed) at [^\n]*\n"
    r"\s*Executed (\d+) tests?\b(?:, with (\d+) tests? skipped\b)?", re.M)

# unittest's "Ran N tests" includes skipped tests; its status line names how many.
UNIT_RUN = re.compile(r"^Ran (\d+) tests?\b", re.M)
UNIT_SKIPPED = re.compile(r"\bskipped=(\d+)")

# Swift Testing counts a skipped test in "Test run with N tests" and prints one line naming it.
# A skipped suite counts a suite, not a test.
SWIFT_RUN = re.compile(r"Test run with (\d+) tests?(?: in \d+ suites?)? (?:passed|failed)")
SWIFT_SKIPPED = re.compile(r"^[^\n]*\bTest \S.* skipped(?:: \"[^\n]*\"|\.)$", re.M)


def _swift_testing_counts(text):
    """Each Swift Testing run's total, less the tests it reported skipped before its summary."""
    counts = []
    skipped = 0
    previous_end = 0
    for run in SWIFT_RUN.finditer(text):
        skipped += len(SWIFT_SKIPPED.findall(text, previous_end, run.start()))
        counts.append(max(int(run.group(1)) - skipped, 0))
        skipped = 0
        previous_end = run.end()
    return counts


def _unittest_counts(text):
    """Each unittest run's total, less the count its following status line reports skipped."""
    runs = list(UNIT_RUN.finditer(text))
    counts = []
    for index, run in enumerate(runs):
        end = runs[index + 1].start() if index + 1 < len(runs) else len(text)
        status = re.search(r"^(?:OK|FAILED)\b(?: \(([^)\n]*)\))?", text[run.end():end], re.M)
        skipped = 0
        if status and status.group(1):
            match = UNIT_SKIPPED.search(status.group(1))
            skipped = int(match.group(1)) if match else 0
        counts.append(max(int(run.group(1)) - skipped, 0))
    return counts


def executed_tests(text):
    """The tests a log reports executed, or None when it reports no count.

    The sum of each XCTest bundle's top-level total, each Swift Testing run and each unittest
    run, less the tests they report skipped: a skipped test establishes no coverage. A wrapper's
    own "Executed N tests" line, one per simulator for example, counts only when the log holds
    no XCTest totals, which it would repeat."""
    suites = list(SUITE_TOTAL.finditer(text))
    top = [(int(match.group(2)), int(match.group(3) or 0)) for match in suites
           if match.group(1) in ("All tests", "Selected tests")]
    within = {match.start(2) for match in suites}
    wrapper = [int(match.group(1)) for match in re.finditer(r"Executed (\d+) tests?\b", text)
               if match.start(1) not in within]
    counts = [max(executed - skipped, 0) for executed, skipped in top] if top else wrapper
    counts += _swift_testing_counts(text)
    counts += _unittest_counts(text)
    return sum(counts) if counts else None


def require_tests(text, minimum=1, expected=None):
    observed = executed_tests(text)
    if expected is not None and observed != expected:
        raise ValueError(f"Expected exactly {expected} executed tests; observed {observed or 0}")
    if observed is None or observed < minimum:
        raise ValueError(f"Expected at least {minimum} executed tests; observed {observed or 0}")
    return observed


# The exit status of a run whose unmeasured results are all that stand between it and a pass.
UNMEASURED = 3

# A test the host left unmeasured skips (XCTest, unittest) or cancels itself (Swift Testing) with a
# reason that begins "Unmeasured:", and swift test and xcodebuild still exit 0. unittest prints the
# reason only when verbose.
UNMEASURED_TEST = re.compile(r"^.*:\d+: -\[[^\]\n]+\] : Test skipped - Unmeasured: .*$"
                             r"|^\S+ Test .* was cancelled after [^:\n]*: \"Unmeasured: .*\"$"
                             r"|^.* \.\.\. skipped 'Unmeasured: .*'$", re.M)


def unmeasured_tests(text):
    """The distinct lines in which a log reports a test unmeasured, in order. A wrapper that
    repeats them in a summary adds none."""
    return list(dict.fromkeys(match.group(0).strip() for match in UNMEASURED_TEST.finditer(text)))


def contained(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe evidence path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Evidence path escapes its root: {relative}")
    return path


def receipt(root, paths):
    return {"schemaVersion": 1, "files": {str(p): sha256(contained(root, p)) for p in paths}}


def verify(root):
    root = Path(root)
    value = json.loads((root / "receipt.json").read_text())
    if value.get("schemaVersion") != 1 or not isinstance(value.get("files"), dict) or not value["files"]:
        raise ValueError("Expected a nonempty version 1 evidence receipt")
    for name, expected in value["files"].items():
        if sha256(contained(root, name)) != expected:
            raise ValueError(f"Evidence changed: {name}")
    return len(value["files"])


def export_xcresults(bundles, destination):
    """Export serially; xcresulttool can contend across simultaneous exports."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for index, bundle in enumerate(bundles):
        target = destination / f"{index:03d}-{Path(bundle).stem}"
        subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(bundle),
                        "--output-path", str(target)], check=True, timeout=300)
