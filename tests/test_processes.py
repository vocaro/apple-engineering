import contextlib
from io import StringIO
from pathlib import Path
import os
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import processes

# Starts each descendant in its own session, as Xcode starts DTServiceHub apart from xcodebuild's
# group, and exits 3 once each is ready and the supervisor has seen it under this root.
ROOT = """
import os, subprocess, sys, time
from pathlib import Path
here = Path(sys.argv[1])
children = [subprocess.Popen([sys.executable, "-c", code, str(here)], start_new_session=True).pid for code in sys.argv[2:]]
(here / "listing").write_text(" ".join(map(str, [os.getpid(), *children])))
(here / "listing").replace(here / "children")
while not all((here / name).exists() for name in ["adopted", *(f"ready-{pid}" for pid in children)]): time.sleep(0.01)
raise SystemExit(3)
"""
READY = "import os, signal, sys, time\nfrom pathlib import Path\nhere = Path(sys.argv[1])\n"
IGNORES_TERM = READY + "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n(here / f'ready-{os.getpid()}').touch()\ntime.sleep(120)"
HANDLES_TERM = READY + ("def stop(*_): (here / 'terminated').touch(); os._exit(0)\n"
                        "signal.signal(signal.SIGTERM, stop)\n(here / f'ready-{os.getpid()}').touch()\ntime.sleep(120)")
FINISHES = READY + ("parent = os.getppid()\n(here / f'ready-{os.getpid()}').touch()\n"
                    "while os.getppid() == parent: time.sleep(0.01)\n(here / 'finished').touch()")
# ROOT that stays once its descendants are adopted, until a signal ends it.
STAYS = ROOT.replace("raise SystemExit(3)", "time.sleep(120)")
# Logs each SIGTERM and takes half a second to shut down after the first, as a test runner can.
COUNTS_TERM = READY + ("stopping = []\n"
                       "def stop(*_):\n    (here / 'terms').open('a').write('TERM\\n')\n    stopping.append(time.monotonic())\n"
                       "signal.signal(signal.SIGTERM, stop)\n"
                       "while not stopping or time.monotonic() - stopping[0] < 0.5: time.sleep(0.01)")


class ProcessTests(unittest.TestCase):
    def outlive_the_root(self, directory, *descendants, root=ROOT, timeout=None, **limits):
        """Supervise ROOT with these descendants; return its result or timeout, stderr and their start identities."""
        real, births, begun = processes.snapshot, {}, time.monotonic()
        def observed():
            # Bound a stall here: a timeout bounds only the root, so a lingering descendant must
            # not hold the run until the test is stopped.
            if time.monotonic() - begun > 30: self.fail("supervision was still waiting after 30 s")
            current = real()
            try: root, *children = map(int, (Path(directory) / "children").read_text().split())
            except FileNotFoundError: return current
            if all(current.get(pid, (None,))[0] == root for pid in children):
                births.update({pid: current[pid][2] for pid in children})
                (Path(directory) / "adopted").touch()
            return current
        def cleanup():
            for pid, birth in births.items():
                if real().get(pid, (0, 0, None))[2] == birth: os.kill(pid, signal.SIGKILL)
        self.addCleanup(cleanup)
        with patch.object(processes, "snapshot", observed), contextlib.redirect_stderr(StringIO()) as error, \
             patch.multiple(processes, create=True, **limits):
            try: result = processes.supervise([sys.executable, "-c", root, directory, *descendants], cwd=directory, timeout=timeout)
            except TimeoutError as expired: result = expired
        current = real()
        self.assertEqual({pid for pid, birth in births.items() if current.get(pid, (0, 0, None))[2] == birth}, set())
        return result, error.getvalue(), births

    def test_descendants_that_outlive_the_root_are_reported_then_stopped_keeping_its_status(self):
        with tempfile.TemporaryDirectory() as directory:
            result, error, births = self.outlive_the_root(directory, IGNORES_TERM, HANDLES_TERM, LINGER=0.2, KILL_AFTER=0.5)
            self.assertEqual(result, 3)
            # SIGTERM came first, so a process that handles it can end cleanly.
            self.assertTrue((Path(directory) / "terminated").exists())
            root = int((Path(directory) / "children").read_text().split()[0])
            self.assertIn("stopping 2 process(es)", error)
            for pid in births:
                self.assertIn(f"{pid} with parent {root}, group {pid}", error)
            self.assertIn("PPID", error)

    def test_a_root_that_exits_in_time_keeps_its_status_when_its_timeout_expires_during_the_grace(self):
        with tempfile.TemporaryDirectory() as directory:
            # The root exits at once; its timeout expires before the grace stops the descendant.
            result, error, _births = self.outlive_the_root(directory, IGNORES_TERM, timeout=2, LINGER=4, KILL_AFTER=0.5)
            self.assertEqual(result, 3)
            self.assertIn("stopping 1 process(es)", error)

    def test_a_descendant_that_ends_within_the_grace_is_awaited_and_never_signaled(self):
        with tempfile.TemporaryDirectory() as directory:
            result, error, _births = self.outlive_the_root(directory, FINISHES, LINGER=30)
            self.assertEqual(result, 3)
            self.assertTrue((Path(directory) / "finished").exists())
            self.assertEqual(error, "")

    def test_nonzero_exit_status_and_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            result = processes.run([sys.executable, "-c", "print('observed'); raise SystemExit(7)"],
                                   cwd=directory, log_path=log)
            self.assertEqual(result, 7)
            self.assertEqual(log.read_text().strip(), "observed")

    def test_a_command_that_cannot_start_raises_not_started(self):
        with tempfile.TemporaryDirectory() as directory:
            unexecutable = Path(directory) / "script.sh"
            unexecutable.write_text("#!/bin/sh\nexit 0\n")
            cases = [([str(Path(directory) / "missing")], directory), ([str(unexecutable)], directory),
                     ([sys.executable, "-c", "pass"], str(Path(directory) / "absent"))]
            for command, cwd in cases:
                with self.subTest(command=command, cwd=cwd):
                    with self.assertRaises(processes.NotStarted) as raised:
                        processes.supervise(command, cwd=cwd)
                    self.assertIsInstance(raised.exception, OSError)

    def test_a_timeout_is_not_a_successful_terminal_result(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                processes.run([sys.executable, "-c", "import time; time.sleep(30)"],
                              cwd=directory, log_path=Path(directory)/"run.log", timeout=0.1)

    def test_a_timeout_stops_descendants_with_sigterm_then_sigkill_and_raises_timed_out_once_they_end(self):
        with tempfile.TemporaryDirectory() as directory:
            # The root stays until the timeout ends it; one descendant handles SIGTERM, one ignores it.
            result, error, _births = self.outlive_the_root(directory, IGNORES_TERM, HANDLES_TERM, root=STAYS,
                                                           timeout=2, KILL_AFTER=0.5)
            self.assertIsInstance(result, processes.TimedOut)
            self.assertTrue((Path(directory) / "terminated").exists())
            self.assertIn("timed out after 2s; sending SIGTERM", error)

    def test_a_timeout_gives_a_command_that_handles_sigterm_one_signal(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(StringIO()):
            with patch.object(processes, "KILL_AFTER", 30), self.assertRaises(processes.TimedOut):
                processes.supervise([sys.executable, "-c", COUNTS_TERM, directory], cwd=directory, timeout=1.5)
            self.assertEqual((Path(directory) / "terms").read_text(), "TERM\n")

    def test_a_stop_reaches_descendants_in_other_sessions_then_raises_interrupted(self):
        # A task stop can deliver its SIGTERM twice, to the process group and to the process; the
        # second must not cut the command's own SIGTERM handling short with SIGKILL.
        self.addCleanup(processes._stops.clear)
        for stops in [[signal.SIGTERM], [signal.SIGTERM, signal.SIGTERM]]:
            with self.subTest(stops=len(stops)), tempfile.TemporaryDirectory() as directory:
                processes._stops.clear()
                here, real, births, begun, marks = Path(directory), processes.snapshot, {}, time.monotonic(), []
                def observed():
                    if time.monotonic() - begun > 30: self.fail("supervision was still waiting after 30 s")
                    current = real()
                    try: root, *children = map(int, (here / "children").read_text().split())
                    except FileNotFoundError: return current
                    # ROOT waits for an adoption that never comes, so only the stop ends it.
                    if not births and all(current.get(pid, (None,))[0] == root for pid in children) \
                            and all((here / f"ready-{pid}").exists() for pid in children):
                        births.update({pid: current[pid][2] for pid in children})
                        for number in stops: processes.request_stop(number)
                    return current
                def cleanup():
                    for pid, birth in births.items():
                        if real().get(pid, (0, 0, None))[2] == birth: os.kill(pid, signal.SIGKILL)
                self.addCleanup(cleanup)
                with patch.object(processes, "snapshot", observed), patch.object(processes, "KILL_AFTER", 0.3), \
                     contextlib.redirect_stderr(StringIO()) as error, self.assertRaises(processes.Interrupted) as raised:
                    processes.supervise([sys.executable, "-c", ROOT, directory, IGNORES_TERM, HANDLES_TERM], cwd=directory,
                                        on_stop=lambda: marks.append((here / "terminated").exists()))
                self.assertEqual(raised.exception.signum, signal.SIGTERM)
                # on_stop ran once, before any process had the signal, and SIGTERM came first.
                self.assertEqual(marks, [False])
                self.assertTrue((here / "terminated").exists())
                current = real()
                self.assertEqual({pid for pid, birth in births.items() if current.get(pid, (0, 0, None))[2] == birth}, set())
                self.assertIn("SIGTERM received; forwarding it to the command", error.getvalue())

    def test_a_stop_before_the_command_starts_runs_nothing(self):
        self.addCleanup(processes._stops.clear)
        processes.request_stop(signal.SIGHUP)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(processes.Interrupted, "SIGHUP before"):
                processes.supervise([sys.executable, "-c", f"open({str(Path(directory) / 'ran')!r}, 'w')"], cwd=directory)
            self.assertFalse((Path(directory) / "ran").exists())
