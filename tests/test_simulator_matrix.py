import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import evidence

ENG = Path(__file__).resolve().parents[1] / "scripts/eng"

# Stand-ins for xcrun simctl and xcodebuild that record what they were asked to do in FAKE_STATE.
# A device type named in FAKE_SLOW_BOOT, FAKE_TEST_FAIL, FAKE_UNMEASURED or FAKE_NO_TESTS boots
# slowly, fails its tests, reports an unmeasured test or runs none. Each test run waits until
# FAKE_MEET devices have started testing, or fails after FAKE_MEET_LIMIT seconds.
XCRUN = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, pathlib, sys, time, uuid
    state = pathlib.Path(os.environ["FAKE_STATE"])
    devices = state / "devices"
    devices.mkdir(parents=True, exist_ok=True)
    tool, action, *rest = sys.argv[1:]
    with (state / "simctl.log").open("a") as log: log.write(" ".join([action, *rest]) + "\\n")
    def kind(udid): return json.loads((devices / udid).read_text())["type"].rsplit(".", 1)[-1]
    if action == "create":
        udid = str(uuid.uuid4()).upper()
        (devices / udid).write_text(json.dumps({"name": rest[0], "type": rest[1], "runtime": rest[2]}))
        print(udid)
    elif action == "bootstatus" and kind(rest[0]) in os.environ.get("FAKE_SLOW_BOOT", ""):
        time.sleep(60)
    elif action == "shutdown":
        sys.exit(0)
    elif action == "delete":
        (devices / rest[0]).unlink()
    elif action == "list":
        print(json.dumps({"devices": {"runtime": [{"udid": path.name, **json.loads(path.read_text())}
                                                  for path in devices.iterdir()]}}))
""")
XCODEBUILD = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, pathlib, sys, time
    state = pathlib.Path(os.environ["FAKE_STATE"])
    action, arguments = sys.argv[1], sys.argv[2:]
    value = lambda flag: arguments[arguments.index(flag) + 1]
    with (state / "xcodebuild.log").open("a") as log: log.write(json.dumps(sys.argv[1:]) + "\\n")
    if action == "build-for-testing":
        if os.environ.get("FAKE_BUILD_FAIL"): sys.exit("** TEST BUILD FAILED **")
        products = pathlib.Path(value("-derivedDataPath")) / "Build/Products"
        products.mkdir(parents=True, exist_ok=True)
        (products / f"{value('-scheme')}_iphonesimulator27.0-arm64.xctestrun").write_text("{}")
        print("** TEST BUILD SUCCEEDED **")
        sys.exit(0)
    udid = value("-destination").split("id=")[1]
    kind = json.loads((state / "devices" / udid).read_text())["type"].rsplit(".", 1)[-1]
    bundle = pathlib.Path(value("-resultBundlePath"))
    if bundle.exists(): sys.exit(f"Existing file at -resultBundlePath {bundle}")
    bundle.mkdir(parents=True)
    (state / f"testing-{udid}").touch()
    deadline = time.monotonic() + float(os.environ.get("FAKE_MEET_LIMIT", "60"))
    while len(list(state.glob("testing-*"))) < int(os.environ.get("FAKE_MEET", "1")):
        if time.monotonic() > deadline: sys.exit(f"{kind} never met the other devices")
        time.sleep(0.05)
    if kind in os.environ.get("FAKE_NO_TESTS", ""): sys.exit(0)
    if kind in os.environ.get("FAKE_UNMEASURED", ""):
        print("/p/T.swift:5: -[P.T testA] : Test skipped - Unmeasured: the host was busy")
    print("Test Suite 'All tests' passed at 2026-10-24 01:00:00.000.")
    print("\\t Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds")
    sys.exit(65 if kind in os.environ.get("FAKE_TEST_FAIL", "") else 0)
""")


class SimulatorMatrixTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        tools = self.root / "bin"
        tools.mkdir()
        for name, source in (("xcrun", XCRUN), ("xcodebuild", XCODEBUILD)):
            (tools / name).write_text(source)
            (tools / name).chmod(0o755)
        self.environment = {"PATH": f"{tools}:{Path(sys.executable).parent}:/usr/bin:/bin", "FAKE_STATE": str(self.state)}

    def run_matrix(self, *arguments, **environment):
        command = [sys.executable, str(ENG), "simulator-tests", "--scheme", "Package-Tests", "--runtime", "iOS-27-0",
                   "--device", "iPhone-17-Pro", "--device", "iPad-Air-13-inch-M4", "--name", "Project", *arguments]
        finished = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                  env={**self.environment, **environment})
        return finished.returncode, finished.stdout + finished.stderr

    def calls(self):
        return [json.loads(line) for line in (self.state / "xcodebuild.log").read_text().splitlines()]

    def assert_every_device_deleted(self):
        simctl = (self.state / "simctl.log").read_text().splitlines()
        created = [line for line in simctl if line.startswith("create ")]
        deleted = [line for line in simctl if line.startswith("delete ")]
        self.assertEqual((len(created), len(deleted)), (2, 2), simctl)
        self.assertEqual(list((self.state / "devices").iterdir()), [])
        self.assertFalse(any("booted" in line.split() for line in simctl))

    def test_one_build_serves_every_device_and_the_devices_test_side_by_side(self):
        status, output = self.run_matrix("--", "-only-testing:T/C", FAKE_MEET="2")
        self.assertEqual(status, 0, output)
        self.assertEqual(evidence.executed_tests(output), 6, output)
        self.assertIn("PASS iPhone-17-Pro: Executed 3 tests", output)
        self.assertIn("PASS iPad-Air-13-inch-M4: Executed 3 tests", output)
        builds = [call for call in self.calls() if call[0] == "build-for-testing"]
        tests = [call for call in self.calls() if call[0] == "test-without-building"]
        self.assertEqual((len(builds), len(tests)), (1, 2))
        self.assertIn("-jobs", builds[0])
        self.assertNotIn("-only-testing:T/C", builds[0])
        self.assertTrue(all(call[-1] == "-only-testing:T/C" for call in tests))
        self.assertTrue(all(call[call.index("-parallel-testing-enabled") + 1] == "NO" for call in tests))
        # The build's destination is a created device, so it builds only that device's architecture.
        udids = {call[call.index("-destination") + 1] for call in tests}
        self.assertIn(builds[0][builds[0].index("-destination") + 1], udids)
        created = [line.split()[1] for line in (self.state / "simctl.log").read_text().splitlines() if line.startswith("create ")]
        self.assertTrue(all(name.startswith("Project-") for name in created), created)
        self.assertEqual(len(set(created)), 2)
        self.assert_every_device_deleted()
        # A second run replaces the first run's result bundles rather than failing on them.
        for path in self.state.glob("testing-*"): path.unlink()
        self.assertEqual(self.run_matrix(FAKE_MEET="2")[0], 0)

    def test_one_device_at_a_time_cannot_meet_the_other(self):
        status, output = self.run_matrix("--jobs", "1", FAKE_MEET="2", FAKE_MEET_LIMIT="1")
        self.assertEqual(status, 1, output)
        self.assertIn("never met the other devices", output)
        self.assert_every_device_deleted()

    def test_a_boot_past_its_limit_leaves_only_that_device_unmeasured(self):
        status, output = self.run_matrix("--boot-timeout", "1", FAKE_SLOW_BOOT="iPad-Air-13-inch-M4")
        self.assertEqual(status, 3, output)
        self.assertIn("UNMEASURED iPad-Air-13-inch-M4: the boot exceeded its limit", output)
        self.assertIn("PASS iPhone-17-Pro: Executed 3 tests", output)
        self.assertEqual(len([call for call in self.calls() if call[0] == "test-without-building"]), 1)
        self.assert_every_device_deleted()

    def test_a_failed_build_tests_no_device(self):
        status, output = self.run_matrix(FAKE_BUILD_FAIL="1")
        self.assertEqual(status, 1, output)
        self.assertIn("FAIL build: status 1", output)
        self.assertIn("FAIL iPhone-17-Pro: not tested: the build failed", output)
        self.assertEqual([call[0] for call in self.calls()], ["build-for-testing"])
        self.assert_every_device_deleted()

    def test_any_device_failure_fails_the_run_and_otherwise_an_unmeasured_test_leaves_it_unmeasured(self):
        cases = [({"FAKE_UNMEASURED": "iPhone-17-Pro"}, 3), ({"FAKE_UNMEASURED": "iPhone-17-Pro",
                  "FAKE_TEST_FAIL": "iPad-Air-13-inch-M4"}, 1), ({"FAKE_NO_TESTS": "iPad-Air-13-inch-M4"}, 1)]
        for environment, expected in cases:
            with self.subTest(environment):
                for path in self.state.glob("testing-*"): path.unlink()
                (self.state / "simctl.log").unlink(missing_ok=True)
                status, output = self.run_matrix(**environment)
                self.assertEqual(status, expected, output)
                self.assert_every_device_deleted()
        self.assertIn("FAIL iPad-Air-13-inch-M4: no tests ran", output)
        status, output = self.run_matrix(FAKE_UNMEASURED="iPhone-17-Pro")
        self.assertEqual(len(evidence.unmeasured_tests(output)), 1, output)

    def test_a_stop_ends_every_device_run_and_deletes_every_device(self):
        command = [sys.executable, str(ENG), "simulator-tests", "--scheme", "Package-Tests", "--runtime", "iOS-27-0",
                   "--device", "iPhone-17-Pro", "--device", "iPad-Air-13-inch-M4"]
        # Three devices never meet, so both runs wait until the stop.
        process = subprocess.Popen(command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   env={**self.environment, "FAKE_MEET": "3"})
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 60
        while len(list(self.state.glob("testing-*"))) < 2:
            self.assertLess(time.monotonic(), deadline, "the devices never started testing")
            time.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        output = process.communicate(timeout=60)[0]
        self.assertEqual(process.returncode, -signal.SIGTERM, output)
        self.assertIn("SIGTERM received; forwarding it", output)
        self.assert_every_device_deleted()

    def test_parallel_workers_on_each_device_are_opt_in(self):
        self.assertEqual(self.run_matrix("--workers", "2")[0], 0)
        tests = [call for call in self.calls() if call[0] == "test-without-building"]
        self.assertTrue(all(call[call.index("-parallel-testing-worker-count") + 1] == "2" for call in tests))

    def test_invalid_arguments_create_no_device(self):
        for arguments in (["--jobs", "0"], ["--device", "iPhone-17-Pro"], ["--build-jobs", "0"]):
            with self.subTest(arguments):
                self.assertEqual(self.run_matrix(*arguments)[0], 2)
        self.assertFalse((self.state / "simctl.log").exists())


if __name__ == "__main__":
    unittest.main()
