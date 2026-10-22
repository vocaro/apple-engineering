from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import processes


class ProcessTests(unittest.TestCase):
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
