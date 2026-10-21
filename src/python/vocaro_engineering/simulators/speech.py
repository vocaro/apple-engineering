"""Simulator speech observation, mute restoration and transcript acceptance mechanisms."""
from datetime import datetime, timezone
import json
import os
import re
import signal
import subprocess
import time
from . import __name__ as _package_name
from vocaro_engineering.voiceover import activation

TEST_ENDED = re.compile(r"^Test Case '.*testCaptureNavigation\]' (passed|failed) \(([\d.]+) seconds\)", re.M)
FAILURES = re.compile(r"^.* error: (?:-\[.*?\] : )?(.*)$", re.M)
# The apps that show a simulator live, by process name: Device Hub from Xcode 27, Simulator.app before.
SIMULATOR_VIEWS = {"DeviceHub": "Device Hub", "Simulator": "Simulator.app"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run(*command, timeout=60):
    """One bounded command: its output, or a RuntimeError that names it."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"No answer in {timeout} s: {' '.join(command)}") from None
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def state(udid, kind, *change, timeout=20, run_command=None):
    """devicectl's reading of a simulator's `audio` or `voiceover` state, after an optional change."""
    run = run_command or globals()["run"]
    if change:
        run("xcrun", "devicectl", "device", "settings", kind, "--device", udid, *change, timeout=timeout)
    answer = run("xcrun", "devicectl", "device", "info", kind, "--device", udid, "--quiet", "--json-output", "-", timeout=timeout)
    return json.loads(answer)["result"]


def keep_muted(session, state_reader=None):
    state = state_reader or globals()["state"]
    """A simulator whose display server restarts comes back at its default volume, VoiceOver still on."""
    try:
        # Briefly: a slow answer must not hold up the watch on the other simulators.
        volume = state(session.udid, "audio", timeout=5)["volume"]
        if volume != 0:
            state(session.udid, "audio", "--volume", "0")
            session.unmuted.append(f"{now()} UNMUTED the volume was {volume}; muted again")
    except (RuntimeError, ValueError, KeyError):
        session.unread.append(f"{now()} VOLUME gave no reading for this check")


def simulator_app():
    """The name of a running app that shows simulators live, or None; it starts nothing.

    Xcode 27 has no Simulator.app: its Device Hub runs as a `DeviceHub` process
    (guides/simulator-testing.md#device-hub).
    """
    for process, name in SIMULATOR_VIEWS.items():
        if subprocess.run(["pgrep", "-x", process], capture_output=True).stdout.strip():
            return name
    return None


def stop(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def events(text):
    return [line.removeprefix("VOICEOVER_EVENT ") for line in text.splitlines() if line.startswith("VOICEOVER_EVENT ")]


def staged(bundle):
    """The probe's output as an unfinished result bundle holds it, for an xcodebuild that will not end."""
    found = [events(path.read_text(errors="replace"))
             for path in bundle.glob("Staging/*/Diagnostics/**/StandardOutputAndStandardError.txt")]
    return max(found, key=len, default=[])


def report(session, *, state_reader=None, test_ended=TEST_ENDED, failure_pattern=FAILURES, activation_module=activation):
    state = state_reader or globals()["state"]
    activation = activation_module
    """Confirm a simulator's VoiceOver is off, write its transcript and print the outcome."""
    log = session.log.read_text(errors="replace") if session.log.exists() else ""
    heard, source = events(log), "xcodebuild's output"
    if len(session.recovered) > len(heard):
        heard, source = session.recovered, "the unfinished result bundle"
    ended = test_ended.search(log)
    failures = sorted(set(failure_pattern.findall(log)))
    counts = re.findall(r"Executed (\d+) tests?[, ]", log)
    if not counts or any(count != "1" for count in counts):
        failures.append("the filtered run did not confirm exactly one executed test")
    if session.activation:
        failures += activation.evidence_failures(log, session.vot.read_text(errors="replace") if session.vot.exists() else "")
    if "Restarting after unexpected exit, crash, or test timeout" in log:
        failures.append("the test runner exited unexpectedly")
    # The probe's last line: without it some steps never ran, whatever the test session reports.
    complete = any(" finished: " in line for line in heard)
    if session.process is None:
        outcome, status = "the probe was not started", 125
    elif ended and ended[1] == "passed" and complete and not failures:
        outcome, status = f"the probe passed in {float(ended[2]):.0f} s", 0
    elif ended:
        outcome, status = f"the probe failed after {float(ended[2]):.0f} s", 1
    else:
        outcome, status = f"the probe {'ran every step but its test never ended' if complete else 'did not finish'}", 124 if session.late else 1
    lines = [f"RESULT {outcome}"] + [f"FAILURE {failure}" for failure in failures]
    if session.note:
        lines.append(f"STOPPED {session.note}; the speech is from {source}")
    try:
        # After a stopped or crashed probe VoiceOver stays on, at whatever volume the simulator has.
        if state(session.udid, "voiceover")["enabled"]:
            enabled = state(session.udid, "voiceover", "--disable")["enabled"]
            lines.append(f"VOICEOVER was left on; it {'is still on' if enabled else 'has been switched off'}")
            status = max(status, 1)
        else:
            lines.append("VOICEOVER off after the run")
        volume = state(session.udid, "audio")["volume"]
        unread = f"; {len(session.unread)} checks during it got no reading" if session.unread else ""
        lines.append(f"VOLUME {volume} after the run{unread}")
        # A simulator that was heard, or could have been, is not a clean run.
        if volume != 0 or session.unmuted:
            status = max(status, 1)
    except (RuntimeError, ValueError, KeyError) as error:
        lines.append(f"VOICEOVER state unknown: {error}")
        status = max(status, 1)
    if session.started is not None:
        lines.append(f"XCODEBUILD ran for {(session.finished or time.monotonic()) - session.started:.0f} s")
    # Ordered by time alone: phrases of one instant keep the order they were spoken in.
    transcript = sorted(session.transcript + heard + session.unmuted + session.unread + [f"{now()} {line}" for line in lines],
                        key=lambda line: line.split(" ", 1)[0])
    path = session.log.with_name(session.log.stem + ".transcript.txt")
    path.write_text("\n".join(transcript) + "\n")
    print(f"{session.kind}: " + "; ".join(lines + session.unmuted))
    print(f"  Transcript: {path}\n  Log: {session.log}\n  Result bundle: {session.bundle}")
    if session.stream is not None:
        print(f"  VoiceOver's log: {session.vot}")
    return status
