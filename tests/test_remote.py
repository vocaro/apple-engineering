import contextlib
import fcntl
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import build_host, cli, config, remote

# Stands in for ssh: the build host is a home directory on this Mac. Like sshd, it runs the
# command in that home through a shell, and git's own ssh transport reaches it the same way.
FAKE_SSH = """#!/bin/sh
while [ $# -gt 0 ]; do
    case "$1" in
        -o|-p|-i|-l|-F|-J) shift 2 ;;
        -*) shift ;;
        *) break ;;
    esac
done
shift
cd "$FAKE_HOME" || exit 255
# The build host has its own heavy-work queue.
HOME="$FAKE_HOME" SHELL="$FAKE_SHELL" HEAVY_SLOT_DIR="$FAKE_SLOTS" SW_GATE_LOCK_FILE="$FAKE_GATE" exec /bin/sh -c "$*"
"""
# A login shell that reads no profile, so the test's PATH reaches the build host.
FAKE_SHELL = """#!/bin/sh
[ "$1" = -l ] && shift
exec /bin/sh "$@"
"""


def git(directory, *arguments):
    return subprocess.run(["git", "-C", str(directory), *arguments], check=True, capture_output=True,
                          text=True).stdout.strip()


def commit_all(directory):
    git(directory, "add", "-A")
    git(directory, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "state")
    return git(directory, "rev-parse", "HEAD")


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.home = base / "build-host-home"
        self.home.mkdir()
        tools = base / "bin"
        tools.mkdir()
        for name, text in [("ssh", FAKE_SSH), ("login-shell", FAKE_SHELL)]:
            (tools / name).write_text(text)
            (tools / name).chmod(0o755)
        # The build host's Python is the Mac's own when it has one: Python 3.9 without Homebrew.
        system = Path("/usr/bin/python3")
        (tools / "python3").symlink_to(system if sys.platform == "darwin" and system.exists() else sys.executable)
        self.toolkit = self.make_toolkit(base / "apple-engineering")
        self.project = base / "example"
        self.project.mkdir()
        python = sys.executable
        lanes = {
            "provision": {"command": [python, "-c", "import pathlib; pathlib.Path('.build').mkdir(exist_ok=True); "
                                      "pathlib.Path('.build/provisioned').touch()"]},
            "check": {"command": [python, "-c", "import os, sys; assert os.path.exists('.build/provisioned'); "
                                  "print('Ran', 2 + len(sys.argv) - 1, 'tests'); print(os.environ['DEVELOPER_DIR'] "
                                  "if 'DEVELOPER_DIR' in os.environ else 'no developer dir')"],
                      "resource": "heavy", "minimumTests": 2},
            "fail": {"command": [python, "-c", "print('Ran 1 tests'); raise SystemExit(3)"]},
            "slow": {"command": [python, "-c", "import os, pathlib, time; "
                                 "pathlib.Path('.build/slow.pid').write_text(str(os.getpid())); time.sleep(60)"],
                     "resource": "heavy"},
            "screen": {"command": [python, "-c", "pass"], "foreground": True},
            "gate": {"command": [python, "-c", "import os; print('Ran 2 tests in', os.getcwd())"],
                     "resource": "heavy", "minimumTests": 2, "buildHost": True},
            "build": {"command": [python, "-c", "print('Ran 1 tests')"], "resource": "heavy"},
            # Asks for a credential only through the store helper, never this Mac's keychain.
            "helpers": {"command": [python, "-c", "import os, subprocess; "
                "env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}; "
                "helpers = subprocess.run(['git', 'config', '--get-all', 'credential.helper'], capture_output=True, "
                "text=True, env=env).stdout.splitlines(); print('helpers', helpers); "
                "fill = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\\nhost=example.invalid\\n\\n', "
                "capture_output=True, text=True, env=env).stdout if helpers[-1:] and 'store' in helpers[-1] else ''; "
                "print([line for line in fill.splitlines() if line.startswith('username=')])"]},
        }
        (self.project / "engineering.json").write_text(json.dumps(
            {"schemaVersion": 1, "name": "Example", "lanes": lanes}, indent=2))
        (self.project / ".gitignore").write_text(".build/\n")
        git(base, "init", "-q", str(self.project))
        self.commit = commit_all(self.project)
        self.environment = patch.dict(os.environ, {
            "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "FAKE_HOME": str(self.home),
            "FAKE_SHELL": str(tools / "login-shell"), "HEAVY_SLOT_DIR": str(base / "slots"),
            "SW_GATE_LOCK_FILE": str(base / "gate"), "HEAVY_POLL_SECONDS": "0.01", "VOCARO_BUILD_HOST": "fake",
            "FAKE_SLOTS": str(base / "build-host-slots"), "FAKE_GATE": str(base / "build-host-gate")})
        self.environment.start()
        os.environ.pop("VOCARO_RESOURCE_TOKEN", None)
        os.environ.pop("DEVELOPER_DIR", None)
        # A run on the real build host hands its git the credential file through these.
        for key in [key for key in os.environ if key.startswith("GIT_CONFIG_") and key != "GIT_CONFIG_GLOBAL"]:
            del os.environ[key]
        self.patches = [patch.object(remote, "TOOLKIT_ROOT", self.toolkit),
                        patch.object(remote, "developer_directory", return_value=None)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in self.patches: item.stop()
        self.environment.stop()
        self.temp.cleanup()

    def make_toolkit(self, root):
        """A committed copy of this toolkit, whose origin is itself, as the build host receives it."""
        for part in ["bin", "integrations", "policies", "agents", "src/python"]:
            shutil.copytree(config.TOOLKIT_ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
        (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "apple-engineering",
                                                           "toolkit": {"path": "."}}))
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        commit_all(root)
        git(root, "remote", "add", "origin", str(root))
        return root

    def eng(self, *arguments):
        with contextlib.redirect_stdout(StringIO()) as output, contextlib.redirect_stderr(StringIO()) as error:
            status = cli.main(["--project", str(self.project), *arguments])
        return status, output.getvalue(), error.getvalue()

    def checkout(self, slot):
        return self.home / remote.ROOT / "checkouts/example" / str(slot) / "example"

    def test_a_lane_runs_at_the_commit_on_the_build_host_after_its_provision_lane(self):
        status, output, error = self.eng("remote", "run", "check")
        self.assertEqual(status, 0, output + error)
        self.assertEqual(git(self.checkout(0), "rev-parse", "HEAD"), self.commit)
        self.assertTrue((self.checkout(0) / ".build/provisioned").exists())
        results = self.project / ".build/engineering/remote/check"
        self.assertIn("Ran 2 tests", (results / "run.log").read_text())
        receipt = json.loads((results / "source.json").read_text())
        self.assertEqual((receipt["commit"], receipt["host"], receipt["result"]["exitStatus"]), (self.commit, "fake", 0))
        self.assertEqual(receipt["toolkit"], git(self.toolkit, "rev-parse", "HEAD"))
        # The build host ran its own admission and wrote its own receipt.
        self.assertEqual(receipt["result"]["receipt"]["project"]["revision"], self.commit)
        self.assertIn("Policy source:", output)
        self.assertIn(f"check at {self.commit[:12]}", error)
        # The toolkit checkout sits beside the project's, at the dispatched commit.
        kit = self.checkout(0).parent / "apple-engineering"
        self.assertEqual(git(kit, "rev-parse", "HEAD"), git(self.toolkit, "rev-parse", "HEAD"))
        # The pushed refs only carried the commits; the checkouts keep them.
        self.assertEqual(git(self.home / remote.ROOT / "repositories/example.git", "for-each-ref"), "")
        self.assertEqual(self.eng("remote", "passed", "check")[0], 0)

    def test_a_whole_lane_counts_only_for_its_exact_commit_and_a_failure_is_its_status(self):
        self.assertEqual(self.eng("remote", "run", "fail")[0], 3)
        self.assertEqual(self.eng("remote", "passed", "fail")[0], 1)
        self.assertEqual(self.eng("remote", "run", "check", "--", "a")[0], 0)
        self.assertIn("Ran 3 tests", (self.project / ".build/engineering/remote/check/run.log").read_text())
        # A filtered run is part of the lane, not a pass of it.
        self.assertEqual(self.eng("remote", "passed", "check")[0], 1)
        self.assertEqual(self.eng("remote", "run", "check")[0], 0)
        self.assertEqual(self.eng("remote", "passed", "check")[0], 0)
        (self.project / "README.md").write_text("next\n")
        commit_all(self.project)
        self.assertEqual(self.eng("remote", "passed", "check")[0], 1)
        self.assertEqual(self.eng("remote", "passed", "check", "--commit", self.commit)[0], 0)

    def test_uncommitted_changes_and_foreground_lanes_are_refused_before_anything_is_sent(self):
        (self.project / "engineering.json").write_text((self.project / "engineering.json").read_text() + "\n")
        status, _output, error = self.eng("remote", "run", "check")
        self.assertEqual(status, 2)
        self.assertIn("commit them first", error)
        git(self.project, "checkout", "--", "engineering.json")
        (self.project / "notes.txt").write_text("untracked\n")
        self.assertIn("commit them first", self.eng("remote", "run", "check")[2])
        (self.project / "notes.txt").unlink()
        self.assertIn("foreground lanes run only here", self.eng("remote", "run", "screen")[2])
        self.assertFalse((self.home / remote.ROOT).exists())

    def test_a_different_xcode_on_the_build_host_is_refused(self):
        local = {**build_host.identity(None), "xcode": "Xcode 99.0\nBuild version 99A1"}
        with patch.object(remote, "developer_directory", return_value=self.temp.name), \
                patch.object(remote.build_host, "identity", return_value=local):
            status, _output, error = self.eng("remote", "run", "check")
        self.assertEqual(status, 2)
        self.assertIn("not the dispatcher's Xcode 99.0", error)
        self.assertFalse(self.checkout(0).exists())

    def test_admit_runs_a_command_in_the_checkout_root(self):
        status, output, _error = self.eng("remote", "admit", "--", sys.executable, "-c",
                                          "import os; print('ran in', os.getcwd())")
        self.assertEqual(status, 0)
        self.assertIn(f"ran in {self.checkout(0).resolve()}", output)
        self.assertIn("ran in", (self.project / ".build/engineering/remote/admit/output.log").read_text())

    @patch.object(remote, "CHECKOUTS", 2)
    def test_a_checkout_a_run_left_changed_is_kept_and_passed_over(self):
        self.assertEqual(self.eng("remote", "run", "check")[0], 0)
        (self.checkout(0) / "stray.txt").write_text("left by a run\n")
        status, output, _error = self.eng("remote", "run", "check")
        self.assertEqual(status, 0)
        self.assertIn("passing over", output)
        self.assertTrue((self.checkout(0) / "stray.txt").exists())
        self.assertEqual(git(self.checkout(1), "rev-parse", "HEAD"), self.commit)
        (self.checkout(1) / "stray.txt").write_text("left by a run\n")
        status, _output, error = self.eng("remote", "run", "check")
        self.assertEqual(status, 2)
        self.assertIn("inspect and remove them", error)

    def test_a_stop_ends_the_build_host_run_and_releases_its_checkout_and_admission(self):
        command = [sys.executable, str(self.toolkit / "bin/eng"), "--project", str(self.project), "remote", "run", "slow"]
        dispatcher = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        marker = self.checkout(0) / ".build/slow.pid"
        deadline = time.monotonic() + 60
        while not marker.exists() and dispatcher.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(marker.exists(), dispatcher.stdout.read().decode() if dispatcher.poll() is not None else "")
        time.sleep(0.2)
        lane = int(marker.read_text())
        dispatcher.send_signal(signal.SIGTERM)
        output = dispatcher.communicate(timeout=60)[0].decode()
        self.assertEqual(dispatcher.returncode, -signal.SIGTERM, output)
        self.assertIn("asking fake to stop the run", output)
        with self.assertRaises(ProcessLookupError):
            os.kill(lane, 0)
        receipt = json.loads((self.project / ".build/engineering/remote/slow/source.json").read_text())
        self.assertTrue(receipt["result"]["stopped"])
        lock = os.open(self.home / remote.ROOT / "checkouts/example/0.lock", os.O_RDWR)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(lock)
        self.assertFalse(Path(os.environ["FAKE_GATE"] + ".warm-push-guard").exists())

    def test_the_build_hosts_credential_file_is_the_runs_only_git_credential_helper(self):
        log = self.project / ".build/engineering/remote/helpers/run.log"
        self.assertEqual(self.eng("remote", "run", "helpers")[0], 0)
        self.assertNotIn("store", log.read_text())
        credentials = self.home / remote.ROOT / "git-credentials"
        credentials.write_text("https://someone:dummy-not-a-token@example.invalid\n")
        self.assertEqual(self.eng("remote", "run", "helpers")[0], 0)
        text = log.read_text()
        # An empty value resets the helpers that system and global configuration name.
        self.assertIn(f"'', 'store --file={credentials}']", text)
        self.assertIn("['username=someone']", text)

    def run_here(self, *arguments):
        """eng run, with this Mac's policy refresh, which would fetch GitHub, left out."""
        with patch.object(cli, "refresh_policy", return_value="policy"):
            return self.eng("run", *arguments)

    def test_a_build_host_lane_runs_there_first(self):
        status, output, error = self.eng("run", "gate")
        self.assertEqual(status, 0, output + error)
        self.assertIn(f"Ran 2 tests in {self.checkout(0).resolve()}",
                      (self.project / ".build/engineering/remote/gate/run.log").read_text())
        self.assertFalse((self.project / ".build/engineering/gate").exists())
        self.assertEqual(self.eng("remote", "passed", "gate")[0], 0)

    def test_a_busy_build_host_sends_the_lane_back_here(self):
        # Exclusive work holds every slot of the build host's queue.
        holder = subprocess.Popen([sys.executable, "-m", "vocaro_engineering.resources", "--exclusive", "--",
                                   sys.executable, "-c", "print('held', flush=True); import time; time.sleep(120)"],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env={
                                      **os.environ, "PYTHONPATH": str(config.TOOLKIT_ROOT / "src/python"),
                                      "HEAVY_SLOT_DIR": os.environ["FAKE_SLOTS"],
                                      "SW_GATE_LOCK_FILE": os.environ["FAKE_GATE"]})
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            status, output, error = self.run_here("gate")
        finally:
            holder.send_signal(signal.SIGTERM)
            holder.wait(timeout=60)
        self.assertEqual(status, 0, output + error)
        self.assertIn("running gate on this Mac: fake did not take it: its heavy-work queue cannot take the lane now",
                      error)
        self.assertIn(f"Ran 2 tests in {self.project.resolve()}",
                      (self.project / ".build/engineering/gate/run.log").read_text())
        # Nothing ran there, so no result of the build host's is recorded.
        self.assertFalse((self.project / ".build/engineering/remote/gate").exists())
        self.assertEqual(self.eng("remote", "passed", "gate")[0], 1)

    def test_a_lane_stays_here_when_asked_unmarked_uncommitted_or_without_a_build_host(self):
        for arguments in [["--here", "gate"], ["build"]]:
            with self.subTest(arguments):
                self.assertEqual(self.run_here(*arguments)[0], 0)
        for setting in [{"VOCARO_BUILD_HOST": "none"}, {}]:
            with self.subTest(setting), patch.dict(os.environ, setting):
                # Without VOCARO_BUILD_HOST, `ssh -G` names no build-host alias.
                if not setting: del os.environ["VOCARO_BUILD_HOST"]
                self.assertEqual(self.run_here("gate")[0], 0)
        self.assertFalse((self.home / remote.ROOT).exists())
        (self.project / "notes.txt").write_text("uncommitted\n")
        status, _output, error = self.run_here("gate")
        self.assertEqual(status, 0)
        self.assertIn("running gate on this Mac", error)
        self.assertIn("commit them first", error)
        self.assertFalse((self.home / remote.ROOT / "checkouts").exists())

    def test_nested_work_runs_its_lane_inside_the_admission_it_inherits(self):
        inner = [sys.executable, str(self.toolkit / "bin/eng"), "--project", str(self.project), "run", "gate"]
        with patch.object(cli, "refresh_policy", return_value="policy"):
            self.assertEqual(self.eng("admit", "--", "/bin/sh", "-c", f"exec {shlex.join(inner)} >/dev/null 2>&1")[0], 0)
        self.assertIn(f"Ran 2 tests in {self.project.resolve()}",
                      (self.project / ".build/engineering/gate/run.log").read_text())
        self.assertFalse((self.home / remote.ROOT).exists())

    def test_only_a_heavy_lane_that_keeps_off_the_screen_may_go_to_the_build_host(self):
        for lane in [{"command": ["true"], "buildHost": True}, {"command": ["true"], "resource": "heavy", "buildHost": 1},
                     {"command": ["true"], "resource": "heavy", "foreground": True, "buildHost": True}]:
            with self.subTest(lane):
                (self.project / "engineering.json").write_text(json.dumps(
                    {"schemaVersion": 1, "name": "Example", "lanes": {"lane": lane}}))
                with self.assertRaises(ValueError): config.load(self.project)

    def test_the_toolkit_runs_itself_without_a_second_checkout(self):
        settings = json.loads((self.toolkit / "engineering.json").read_text())
        # Heavy, so the build host's policy refresh fetches the toolkit's origin from its own checkout.
        settings["lanes"] = {"check": {"command": [sys.executable, "-c", "print('Ran 1 tests')"], "minimumTests": 1,
                                       "resource": "heavy"}}
        (self.toolkit / "engineering.json").write_text(json.dumps(settings))
        commit = commit_all(self.toolkit)
        with contextlib.redirect_stdout(StringIO()), contextlib.redirect_stderr(StringIO()) as error:
            self.assertEqual(cli.main(["--project", str(self.toolkit), "remote", "run", "check"]), 0, error.getvalue())
        slot = self.home / remote.ROOT / "checkouts/apple-engineering/0"
        self.assertEqual([path.name for path in slot.iterdir()], ["apple-engineering"])
        self.assertEqual(git(slot / "apple-engineering", "rev-parse", "HEAD"), commit)
        self.assertEqual([path.name for path in (self.home / remote.ROOT / "repositories").iterdir()],
                         ["apple-engineering.git"])


if __name__ == "__main__":
    unittest.main()
