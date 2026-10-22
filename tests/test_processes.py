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


class ProcessTests(unittest.TestCase):
    def outlive_the_root(self, directory, *descendants, **limits):
        """Supervise ROOT with these descendants; return its result, stderr and their start identities."""
        real, births = processes.snapshot, {}
        def observed():
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
            # The timeout bounds a stall: a lingering descendant must not hold the run until it.
            result = processes.supervise([sys.executable, "-c", ROOT, directory, *descendants], cwd=directory, timeout=30)
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
