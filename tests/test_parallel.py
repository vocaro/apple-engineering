import contextlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import cli, evidence

ENG = Path(__file__).resolve().parents[1] / "scripts/eng"

# Waits until the file named by its second argument exists, writing the first: two such commands
# end only when both run at once. The third argument bounds the wait in seconds.
RENDEZVOUS = textwrap.dedent("""
    import pathlib, sys, time
    mine, theirs, limit = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), float(sys.argv[3])
    mine.touch()
    deadline = time.monotonic() + limit
    while not theirs.exists():
        if time.monotonic() > deadline: sys.exit(f"{theirs.name} never appeared")
        time.sleep(0.05)
    print("Ran 1 test")
""")


def module(name, body):
    return name, textwrap.dedent("""
        import os, pathlib, sys, time, unittest
        HERE = pathlib.Path(__file__).resolve().parent
    """) + textwrap.dedent(body)


# A unittest module that meets another at a rendezvous, as RENDEZVOUS does.
def meeting(mine, theirs, group=None):
    return textwrap.dedent(f"""
        {f'serial_group = "{group}"' if group else ''}
        class Meet(unittest.TestCase):
            def test_meet(self):
                (HERE / "{mine}.pid").write_text(str(os.getpid()))
                (HERE / "{mine}").touch()
                deadline = time.monotonic() + float(os.environ["MEET_LIMIT"])
                while not (HERE / "{theirs}").exists():
                    if time.monotonic() > deadline: self.fail("{theirs} never appeared")
                    time.sleep(0.05)
    """)


class UnittestRunnerTests(unittest.TestCase):
    def suite(self, *modules):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name, source in modules:
            (root / f"{name}.py").write_text(source)
        return root

    def run_suite(self, root, *arguments, limit=60):
        finished = subprocess.run([sys.executable, str(ENG), "unittest", "-s", str(root), *arguments],
                                  capture_output=True, text=True, env={"MEET_LIMIT": str(limit), "PATH": "/usr/bin:/bin"})
        return finished.returncode, finished.stdout + finished.stderr

    def test_modules_run_side_by_side_and_one_job_runs_them_one_after_another(self):
        root = self.suite(module("test_left", meeting("left", "right")), module("test_right", meeting("right", "left")))
        status, output = self.run_suite(root, "-j", "2")
        self.assertEqual(status, 0, output)
        self.assertNotEqual((root / "left.pid").read_text(), (root / "right.pid").read_text())
        self.assertIn("eng unittest: 2 tests in 2 processes, 2 at a time", output)
        # The negative control: one at a time, neither module can meet the other.
        for marker in ("left", "right", "left.pid", "right.pid"): (root / marker).unlink()
        status, output = self.run_suite(root, "-j", "1", limit=1)
        self.assertEqual(status, 1, output)
        self.assertIn("right never appeared", output)

    def test_a_serial_group_runs_its_modules_in_one_process(self):
        root = self.suite(module("test_left", meeting("left", "right", group="shared")),
                          module("test_right", meeting("right", "left", group="shared")),
                          module("test_alone", "class Alone(unittest.TestCase):\n    def test_alone(self): pass\n"))
        status, output = self.run_suite(root, "-j", "3", limit=1)
        # The group's modules never run at once, so the first cannot meet the second.
        self.assertEqual(status, 1, output)
        self.assertIn("== group:shared: FAILED (failures=1) (2 tests", output)
        self.assertIn("== test_alone: OK (1 tests", output)
        self.assertEqual((root / "left.pid").read_text(), (root / "right.pid").read_text())

    def test_each_test_counts_once_and_failures_and_import_errors_fail_the_run(self):
        root = self.suite(
            module("test_pass", "class P(unittest.TestCase):\n    def test_a(self): pass\n    def test_b(self): pass\n"),
            module("test_fail", "class F(unittest.TestCase):\n    def test_a(self): self.fail('planted')\n"),
            module("test_broken", "import a_module_that_does_not_exist\n"))
        status, output = self.run_suite(root, "-v")
        self.assertEqual(status, 1, output)
        self.assertIn("FAILED: test_broken (FAILED (errors=1), status 1), test_fail (FAILED (failures=1), status 1)", output)
        self.assertIn("No module named 'a_module_that_does_not_exist'", output)
        # The runner's own summary is not a "Ran N tests" line, so a lane counts each test once.
        self.assertEqual(evidence.executed_tests(output), 4)

    def test_a_passing_suite_reports_its_unmeasured_skips_and_its_count(self):
        root = self.suite(module("test_mixed", """
            class M(unittest.TestCase):
                def test_measured(self): pass
                def test_busy(self): self.skipTest("Unmeasured: the host was busy")
        """))
        status, output = self.run_suite(root, "-v")
        self.assertEqual(status, 0, output)
        self.assertEqual(evidence.executed_tests(output), 2)
        self.assertEqual(len(evidence.unmeasured_tests(output)), 1, output)

    def test_a_process_that_ends_before_its_tests_have_run_fails(self):
        root = self.suite(module("test_exits", """
            class E(unittest.TestCase):
                def test_exits(self): os._exit(0)
                def test_never_runs(self): pass
        """))
        status, output = self.run_suite(root)
        self.assertEqual(status, 1, output)
        self.assertIn("FAILED: test_exits (ran 0 of 2 tests)", output)

    def test_a_class_or_test_split_runs_each_in_its_own_process(self):
        root = self.suite(module("test_split", """
            class A(unittest.TestCase):
                def test_one(self): (HERE / f"one").write_text(str(os.getpid()))
                def test_two(self): (HERE / f"two").write_text(str(os.getpid()))
            class B(unittest.TestCase):
                def test_three(self): (HERE / f"three").write_text(str(os.getpid()))
        """))
        pids = lambda: [(root / name).read_text() for name in ("one", "two", "three")]
        self.assertEqual(self.run_suite(root, "--split", "class")[0], 0)
        one, two, three = pids()
        self.assertEqual(one, two)
        self.assertNotEqual(one, three)
        self.assertEqual(self.run_suite(root, "--split", "test")[0], 0)
        self.assertEqual(len(set(pids())), 3)

    def test_a_suite_without_tests_is_not_a_pass(self):
        root = self.suite(module("helper", "VALUE = 1\n"))
        status, output = self.run_suite(root)
        self.assertEqual(status, 5, output)
        self.assertIn("no tests found", output)

    def test_jobs_needs_at_least_one(self):
        root = self.suite()
        self.assertEqual(self.run_suite(root, "-j", "0")[0], 2)


class LaneGroupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def configure(self, lanes):
        (self.root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Group", "lanes": lanes}))

    def run_lane(self, *arguments):
        with patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()) as output, \
                contextlib.redirect_stderr(StringIO()) as error:
            status = cli.main(["--project", str(self.root), "run", *arguments])
        return status, output.getvalue() + error.getvalue()

    def meet(self, mine, theirs, limit):
        return {"command": [sys.executable, "-c", RENDEZVOUS, str(self.root / mine), str(self.root / theirs), str(limit)],
                "minimumTests": 1}

    def test_a_group_runs_its_lanes_side_by_side_and_serial_runs_them_in_turn(self):
        self.configure({"left": self.meet("left", "right", 60), "right": self.meet("right", "left", 60),
                        "both": {"parallel": ["left", "right"]}})
        status, output = self.run_lane("both")
        self.assertEqual(status, 0, output)
        self.assertIn("PASS left", output)
        self.assertIn("PASS right", output)
        receipt = json.loads((self.root / ".build/engineering/both/source.json").read_text())
        self.assertEqual((receipt["exitStatus"], receipt["jobs"], sorted(receipt["lanes"])), (0, 2, ["left", "right"]))
        self.assertIn("Ran 1 test", (self.root / ".build/engineering/both/lanes/left.log").read_text())
        # The negative control: in turn, the first lane cannot meet the second.
        self.configure({"left": self.meet("late", "never", 1), "right": self.meet("never", "late", 1),
                        "both": {"parallel": ["left", "right"]}})
        status, output = self.run_lane("--serial", "both")
        self.assertEqual(status, 1, output)
        self.assertIn("never never appeared", output)
        self.assertEqual(json.loads((self.root / ".build/engineering/both/source.json").read_text())["jobs"], 1)

    def test_any_failure_fails_the_group_and_otherwise_any_unmeasured_lane_leaves_it_unmeasured(self):
        say = lambda text, status=0, **lane: {"command": [sys.executable, "-c", f"print({text!r}); raise SystemExit({status})"],
                                              **lane}
        unmeasured = "/p/T.swift:5: -[P.T testA] : Test skipped - Unmeasured: busy\nRan 1 test"
        lanes = {"pass": say("Ran 2 tests", minimumTests=2), "fail": say("Ran 2 tests", 1),
                 "unmeasured": say(unmeasured), "short": say("Ran 1 test", minimumTests=2),
                 "slow": {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout": 1}}
        cases = {("pass",): 0, ("pass", "unmeasured"): 3, ("pass", "slow"): 3, ("pass", "unmeasured", "fail"): 1,
                 ("pass", "short"): 1}
        for members, expected in cases.items():
            with self.subTest(members):
                self.configure({**lanes, "group": {"parallel": list(members)}})
                status, output = self.run_lane("group")
                self.assertEqual(status, expected, output)
                # Every lane runs to its own end, whatever the others did.
                self.assertEqual(sorted(json.loads((self.root / ".build/engineering/group/source.json").read_text())["lanes"]),
                                 sorted(members))
        self.assertIn("Expected at least 2 executed tests; observed 1", output)
        self.assertIn("FAIL short", output)

    def test_a_group_takes_no_arguments_and_serial_needs_a_group(self):
        self.configure({"one": {"command": [sys.executable, "-c", "pass"]}, "group": {"parallel": ["one"]}})
        for arguments in (["group", "--", "x"], ["--expect", "1", "group"], ["--serial", "one"]):
            with self.subTest(arguments):
                self.assertEqual(self.run_lane(*arguments)[0], 2)
        self.assertFalse((self.root / ".build/engineering/group").exists())

    def test_a_group_names_runnable_lanes_and_holds_their_heaviest_resource(self):
        command = {"command": ["true"]}
        lanes = {"one": command, "two": command, "heavy": {**command, "resource": "heavy"},
                 "screen": {**command, "resource": "heavy", "foreground": True}}
        invalid = [{"parallel": []}, {"parallel": ["one", "one"]}, {"parallel": ["missing"]},
                   {"parallel": ["one", "inner"]}, {"parallel": ["heavy"]},
                   {"parallel": ["heavy"], "resource": "heavy", "foreground": True},
                   {"parallel": ["screen"], "resource": "heavy"}, {"parallel": ["one", "two"], "jobs": 0},
                   {"parallel": ["one", "two"], "jobs": 3}, {"parallel": ["one"], "command": ["true"]},
                   {"parallel": ["one"], "buildHost": True}, {"parallel": ["one"], "minimumTests": 1}]
        for group in invalid:
            with self.subTest(group):
                self.configure({**lanes, "inner": {"parallel": ["one"]}, "group": group})
                self.assertEqual(self.run_lane("group")[0], 2)
        for group in ({"parallel": ["one", "two"], "jobs": 1}, {"parallel": ["heavy", "one"], "resource": "exclusive",
                                                                "buildHost": True}):
            with self.subTest(group):
                self.configure({**lanes, "group": group})
                cli.load(self.root)


if __name__ == "__main__":
    unittest.main()
