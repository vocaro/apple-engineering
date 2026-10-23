import contextlib
from io import StringIO
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import cli, config, docs, evidence, processes, resources


class ConfigurationTests(unittest.TestCase):
    def test_initialization_preserves_existing_files_and_never_runs_a_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("Existing owner rules\n")
            with patch.object(subprocess, "run", side_effect=AssertionError("initialization ran a process")), contextlib.redirect_stdout(StringIO()):
                self.assertEqual(cli.main(["--project", directory, "init", "--capability", "voiceover"]), 0)
            self.assertEqual((root / "AGENTS.md").read_text(), "Existing owner rules\n")
            self.assertTrue((root / "scripts/eng").exists())
            self.assertEqual(config.load(root)["capabilities"], ["voiceover"])

    def test_unknown_capabilities_and_conflicting_simulator_ownership_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for capabilities in [["typo"], ["simulator-disposable", "simulator-pool"]]:
                (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example", "capabilities": capabilities}))
                with self.assertRaises(ValueError): config.load(root)

    def test_every_capability_has_guidance_and_a_schema_entry(self):
        schema = json.loads((config.TOOLKIT_ROOT / "schemas/engineering.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["capabilities"]["items"]["enum"]), config.CAPABILITIES)
        for capability in config.CAPABILITIES:
            self.assertTrue((config.TOOLKIT_ROOT / "agents/capabilities" / f"{capability}.md").is_file(), capability)

    def test_lane_commands_are_argv_not_shell_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example",
                "lanes": {"bad": {"command": "printf success"}}}))
            with self.assertRaises(ValueError): config.load(root)

    def test_missing_prerequisites_are_reported_without_starting_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example"}))
            with patch.object(cli.shutil, "which", return_value=None), patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()):
                self.assertEqual(cli.main(["--project", directory, "doctor"]), 1)

    def test_doctor_warns_when_heavy_capabilities_have_no_heavy_or_exclusive_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            light = {"check": {"command": ["true"]}}
            cases = [(["voiceover"], light, True), (["simulator-pool", "measurement"], {}, True),
                     (["voiceover"], {**light, "test": {"command": ["true"], "resource": "heavy"}}, False),
                     (["measurement"], {"gate": {"command": ["true"], "resource": "exclusive"}}, False),
                     (["packaging"], light, False)]
            for capabilities, lanes, warned in cases:
                with self.subTest(capabilities=capabilities, lanes=sorted(lanes)):
                    (Path(directory) / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example",
                        "capabilities": capabilities, "lanes": lanes}))
                    with patch.object(cli.shutil, "which", return_value="/usr/bin/true"), patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()) as output:
                        # A warning is not a missing prerequisite.
                        self.assertEqual(cli.main(["--project", directory, "doctor"]), 0)
                    warnings = json.loads(output.getvalue())["warnings"]
                    self.assertEqual(bool(warnings), warned, warnings)
                    for capability in capabilities if warned else []:
                        self.assertIn(capability, warnings[0])

    def test_instructions_note_a_toolkit_checkout_behind_origin_main_without_fetching(self):
        with tempfile.TemporaryDirectory() as directory:
            clone, plain = Path(directory) / "clone", Path(directory) / "plain"
            plain.mkdir()
            git = ["git", "-C", str(clone), "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            for message in ["first", "second"]:
                subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", message], check=True)
            with patch.object(cli.subprocess, "run", wraps=subprocess.run) as run:
                self.assertEqual(cli.behind_main(clone), 0)
                subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
                self.assertEqual(cli.behind_main(clone), 0)
                subprocess.run([*git, "checkout", "-q", "--detach", "HEAD~1"], check=True)
                self.assertEqual(cli.behind_main(clone), 1)
                self.assertEqual(cli.behind_main(plain), 0)
            self.assertEqual([call for call in run.call_args_list if "fetch" in call.args[0]], [])
            (Path(directory) / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example"}))
            for behind in [2, 0]:
                with self.subTest(behind=behind), patch.object(cli, "behind_main", return_value=behind), contextlib.redirect_stdout(StringIO()) as output:
                    self.assertEqual(cli.main(["--project", directory, "instructions"]), 0)
                    self.assertEqual("lacks 2 commit(s) of origin/main as last fetched" in output.getvalue(), bool(behind))
                    self.assertIn("Common engineering rules", output.getvalue())

    def test_local_launcher_works_offline_in_a_new_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(StringIO()): cli.main(["--project", directory, "init"])
            result = subprocess.run([sys.executable, str(Path(directory) / "scripts/eng"), "instructions"],
                capture_output=True, text=True, env={**os.environ, "PATH": str(Path(sys.executable).parent)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Common engineering rules", result.stdout)


    def test_generated_lane_outputs_do_not_change_the_project_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", directory], check=True)
            with contextlib.redirect_stdout(StringIO()): cli.main(["--project", directory, "init"])
            path = root / "engineering.json"
            value = json.loads(path.read_text())
            value["lanes"] = {"check": {"command": [sys.executable, "-c", "print('checked')"]}}
            path.write_text(json.dumps(value))
            before = config.source_identity(root)
            self.assertEqual(cli.main(["--project", directory, "run", "check"]), 0)
            self.assertEqual(config.source_identity(root), before)

    def test_lane_arguments_reach_its_command_and_a_filtered_run_needs_a_test_or_its_expected_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Reports one executed test for each argument it receives.
            count = [sys.executable, "-c", "import sys; print('Ran', len(sys.argv) - 1, 'tests')"]
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Lanes", "lanes": {
                "test": {"command": count, "minimumTests": 5}, "check": {"command": [sys.executable, "-c", "pass"]}}}))
            cases = [(["test"], 2, None),  # the whole lane still needs its minimumTests
                     (["test", "--", "a", "b"], 0, ["a", "b"]),
                     (["test", "--expect", "2", "--", "a", "b"], 0, ["a", "b"]),
                     (["--expect", "2", "test", "--", "a", "b"], 0, ["a", "b"]),
                     (["test", "--expect", "3", "--", "a", "b"], 2, ["a", "b"]),
                     (["test", "--expect", "1", "--", "a", "b"], 2, ["a", "b"]),
                     (["test", "--", "a", "--", "b"], 0, ["a", "--", "b"]),
                     (["test", "--expect", "0", "--", "a"], 2, "not run"),
                     (["check", "--", "x"], 0, ["x"])]  # a lane without minimumTests counts no tests
            for arguments, status, passed in cases:
                with self.subTest(arguments):
                    receipt = root / ".build/engineering" / arguments[arguments[0] == "--expect" and 2] / "source.json"
                    receipt.unlink(missing_ok=True)
                    with patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stderr(StringIO()) as error:
                        self.assertEqual(cli.main(["--project", directory, "run", *arguments]), status, error.getvalue())
                    if passed == "not run":
                        self.assertFalse(receipt.exists())
                        continue
                    recorded = json.loads(receipt.read_text())
                    self.assertEqual(recorded["arguments"], passed or [])
                    self.assertEqual(recorded["command"][3:], passed or [])
            self.assertIn("Expected exactly 3 executed tests; observed 2", self.run_lane(directory, "test", "--expect", "3", "--", "a", "b"))
            for arguments in [["run", "test", "-k", "x"], ["doctor", "--", "x"]]:
                with self.subTest(arguments), self.assertRaises(SystemExit), contextlib.redirect_stderr(StringIO()):
                    cli.main(["--project", directory, *arguments])

    def run_lane(self, directory, *arguments):
        with patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stderr(StringIO()) as error:
            cli.main(["--project", directory, "run", *arguments])
        return error.getvalue()



class EvidenceTests(unittest.TestCase):
    def test_zero_tests_cannot_pass_but_a_swift_testing_run_is_not_its_zero_test_xctest_shim(self):
        for text in ["** TEST SUCCEEDED **", "Executed 0 tests, with 0 failures", "Ran 0 tests in 0.000s\nOK", "Test run with 0 tests in 0 suites passed"]:
            with self.assertRaises(ValueError): evidence.require_tests(text)
        self.assertEqual(evidence.require_tests("Executed 0 tests, with 0 failures\nTest run with 30 tests in 2 suites passed after 1s"), 30)

        self.assertEqual(evidence.require_tests("Ran 43 tests in 0.5s\n\nOK",43),43)

    def test_an_expected_count_must_match_exactly(self):
        self.assertEqual(evidence.require_tests("Executed 0 tests\nTest run with 3 tests in 1 suite passed", expected=3), 3)
        for text in ["Ran 2 tests", "Ran 4 tests", "** TEST SUCCEEDED **"]:
            with self.subTest(text), self.assertRaisesRegex(ValueError, "exactly 3"):
                evidence.require_tests(text, expected=3)

    def test_changed_missing_and_escaping_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "result.txt").write_text("observed")
            receipt = evidence.receipt(root, ["result.txt"])
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual(evidence.verify(root), 1)
            (root / "result.txt").write_text("changed")
            with self.assertRaises(ValueError): evidence.verify(root)
            for path in ["../elsewhere", "/tmp/elsewhere"]:
                with self.assertRaises(ValueError): evidence.contained(root, path)
            (root / "outside").symlink_to(root.parent)
            with self.assertRaises(ValueError): evidence.contained(root, "outside/secret")

    def test_exports_are_sequential_and_preserve_bundle_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(evidence.subprocess, "run") as run:
            evidence.export_xcresults(["a.xcresult", "b.xcresult"], directory)
            self.assertEqual(run.call_count, 2)
            self.assertIn("a.xcresult", run.call_args_list[0].args[0])
            self.assertIn("b.xcresult", run.call_args_list[1].args[0])


class DocumentationTests(unittest.TestCase):
    def test_case_mismatches_missing_links_and_large_instructions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target.md").write_text("# Target\n")
            (root / "README.md").write_text("[fine](target.md)\n[wrong](Target.md)\n[missing](absent.md)\n")
            (root / "AGENTS.md").write_text("x" * 32768)
            failures = docs.check(root)
            self.assertEqual(len(failures), 3, failures)

    def test_all_inventory_items_have_subjects_and_source_links(self):
        value = json.loads((config.TOOLKIT_ROOT / "knowledge/index.json").read_text())
        self.assertEqual([e["id"] for e in value["entries"]], list(range(1, len(value["entries"]) + 1)))
        for entry in value["entries"]:
            path = config.TOOLKIT_ROOT / entry["path"]
            self.assertTrue(path.is_file())
            text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
            self.assertIn("## " + entry["title"], text.splitlines(), entry["path"])
            self.assertTrue(entry["sources"], entry["title"])

    def test_what_agents_are_told_to_read_names_the_admission_commands(self):
        """eng instructions, eng policy refresh and eng --help each say how to admit heavy work."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example"}))
            with contextlib.redirect_stdout(StringIO()) as instructions:
                cli.main(["--project", directory, "instructions"])
        with contextlib.redirect_stdout(StringIO()) as usage, self.assertRaises(SystemExit):
            cli.main(["--help"])
        # The policy refresh prints this document from main.
        policy = (config.TOOLKIT_ROOT / "policies/shared-host.md").read_text()
        for name, text in [("instructions", instructions.getvalue()), ("help", usage.getvalue()), ("policy", policy)]:
            text = " ".join(text.split())
            with self.subTest(name):
                self.assertIn("eng admit -- COMMAND", text)
                self.assertIn("--exclusive", text)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HEAVY_SLOT_DIR": str(root / "slots"), "HEAVY_SLOTS": "2",
            "HEAVY_SLOTS_MAX": "3", "HEAVY_POLL_SECONDS": "0.01", "SW_GATE_LOCK_FILE": str(root / "gate")})
        self.env.start()
        self.saved = os.environ.pop(resources.TOKEN, None)

    def tearDown(self):
        if self.saved is not None: os.environ[resources.TOKEN] = self.saved
        else: os.environ.pop(resources.TOKEN, None)
        self.env.stop()
        self.temp.cleanup()

    def test_private_command_tmpdirs_do_not_create_separate_host_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment.pop("HEAVY_SLOT_DIR", None)
            command = [sys.executable, "-c", "from vocaro_engineering.resources import slot_directory; print(slot_directory())"]
            environment["PYTHONPATH"] = str(config.TOOLKIT_ROOT / "src/python")
            outputs = []
            for name in ["first", "second"]:
                folder = Path(directory) / name
                folder.mkdir()
                result = subprocess.check_output(command, text=True, env={**environment, "TMPDIR": str(folder)})
                outputs.append(result.strip())
            self.assertEqual(outputs[0], outputs[1])

    def hold(self, *slots):
        directory = resources.slot_directory()
        directory.mkdir(parents=True, exist_ok=True)
        for slot in slots:
            _slot, fd = resources.take_slot(directory, slot + 1, start=slot)
            os.write(fd, b"other holder\n")
            self.addCleanup(os.close, fd)

    def test_spare_capacity_admits_jobs_beyond_the_guaranteed_slots_up_to_the_maximum(self):
        self.hold(0, 1)
        os.environ["HEAVY_SETTLE_SECONDS"] = "0"
        with patch.object(resources.os, "getloadavg", return_value=(1.0, 1.0, 1.0)), patch.object(resources, "memory_normal", return_value=True), contextlib.redirect_stderr(StringIO()):
            with resources.Admission("extra", timeout=0) as admitted:
                self.assertEqual([slot for slot, _fd in admitted.descriptors], [2])
            self.hold(2)
            with self.assertRaisesRegex(TimeoutError, "all 3 slots are busy"):
                with resources.Admission("beyond", timeout=0): pass

    def test_load_memory_pressure_or_an_unsettled_admission_withholds_extra_slots(self):
        self.hold(0, 1)
        os.environ["HEAVY_LOAD_LIMIT"] = "4"
        cases = [("load 9.0 is at or above 4", (9.0, 9.0, 9.0), True, "0"),
            ("memory pressure is not normal", (1.0, 1.0, 1.0), False, "0"),
            ("does not yet show the job admitted", (1.0, 1.0, 1.0), True, "3600")]
        for reason, load, memory, settle in cases:
            with self.subTest(reason):
                os.environ["HEAVY_SETTLE_SECONDS"] = settle
                with patch.object(resources.os, "getloadavg", return_value=load), patch.object(resources, "memory_normal", return_value=memory), contextlib.redirect_stderr(StringIO()) as error:
                    with self.assertRaisesRegex(TimeoutError, reason):
                        with resources.Admission("blocked", timeout=0): pass
                self.assertIn(reason, error.getvalue())

    def test_adaptive_limits_default_to_the_host_and_reject_a_maximum_below_the_guarantee(self):
        os.environ.pop("HEAVY_SLOTS_MAX")
        self.assertEqual(resources.Admission("default").maximum, max(2, (os.cpu_count() or 1) // 2))
        os.environ["HEAVY_SLOTS_MAX"] = "1"
        with self.assertRaises(ValueError): resources.Admission("invalid")

    def test_exclusive_admission_holds_all_legacy_slots_and_nested_calls_reuse_it(self):
        with resources.Admission("test", exclusive=True, timeout=0):
            self.assertIsNone(resources.take_slot(resources.slot_directory(), 3))
            with resources.Admission("nested", timeout=0) as nested:
                self.assertTrue(nested.reused)
            self.assertTrue(Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard").exists())
        self.assertFalse(Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard").exists())

    def test_exclusive_escalation_inside_shared_work_fails_instead_of_deadlocking(self):
        with resources.Admission("shared", timeout=0):
            with self.assertRaises(RuntimeError):
                with resources.Admission("exclusive", exclusive=True, timeout=0): pass

    def test_foreign_or_uncertain_guard_is_never_reclaimed(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        guard.write_text('{"keeper": 123456}')
        with self.assertRaises(TimeoutError):
            with resources.Admission("blocked", timeout=0): pass
        guard.unlink()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            with resources.Admission("owned", timeout=0): raise RuntimeError("uncertain")
        self.assertTrue(guard.exists())
        with self.assertRaises(TimeoutError):
            with resources.Admission("blocked", timeout=0): pass

    def test_a_killed_owner_does_not_strand_the_release_of_a_job_admitted_beside_it(self):
        # A job admitted beside one killed by SIGKILL changes only its own entry when it leaves.
        # Changing nothing stranded the queue for 80 minutes (2026-10-22): every job that finished
        # while the killed job's entry stood became another dead owner.
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        holder = ("import sys\nfrom vocaro_engineering import resources\n"
                  "with resources.Admission('killed', timeout=0):\n    print(flush=True)\n    sys.stdin.read()\n")
        environment = {**os.environ, "PYTHONPATH": str(config.TOOLKIT_ROOT / "src/python")}
        for failure in [None, RuntimeError]:
            with self.subTest(failure=failure):
                guard.unlink(missing_ok=True)
                # Closing its stdin releases the holder if an assertion fails before the kill.
                with subprocess.Popen([sys.executable, "-c", holder], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True, env=environment) as killed:
                    self.assertEqual(killed.stdout.readline(), "\n")
                    recorded = json.loads(guard.read_text())["owners"]
                    with contextlib.redirect_stderr(StringIO()), contextlib.suppress(RuntimeError):
                        with resources.Admission("beside", timeout=0) as beside:
                            killed.kill()
                            killed.wait()
                            if failure: raise failure("children may remain")
                owners = json.loads(guard.read_text())["owners"]
                if failure:
                    self.assertTrue(owners.pop(beside.identity).get("uncertain"))
                self.assertEqual(owners, recorded)
                # The killed job's entry still awaits attended recovery.
                with self.assertRaises(TimeoutError), contextlib.redirect_stderr(StringIO()):
                    with resources.Admission("blocked", timeout=0): pass

    def test_zero_test_failure_releases_a_confirmed_finished_lane(self):
        root = Path(self.temp.name)
        (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Zero",
            "lanes": {"empty": {"command": ["unused"], "resource": "heavy", "minimumTests": 1}}}))
        def finished(*args, **kwargs):
            kwargs["log_path"].write_text("Executed 0 tests, with 0 failures")
            return 0
        with patch.object(cli, "refresh_policy", return_value="policy"), patch.object(cli, "source_identity", return_value={}), patch.object(cli.processes, "run", side_effect=finished), contextlib.redirect_stderr(StringIO()):
            self.assertEqual(cli.main(["--project", str(root), "run", "empty"]), 2)
        self.assertFalse(Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard").exists())

    def test_a_shared_owner_cannot_forge_exclusive_admission(self):
        with resources.Admission("shared", timeout=0):
            token = json.loads(os.environ[resources.TOKEN])
            token["exclusive"] = True
            os.environ[resources.TOKEN] = json.dumps(token)
            with self.assertRaisesRegex(RuntimeError, "capability"):
                resources.inherited(exclusive=True)

    def test_forged_inherited_descriptor_is_rejected(self):
        os.environ[resources.TOKEN] = json.dumps({"schemaVersion": 1, "locks": [{"fd": 999999, "path": "/not-a-lock", "nonce": "bad"}]})
        with self.assertRaises(RuntimeError): resources.inherited()

    def admit(self, *arguments):
        root = Path(self.temp.name)
        (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Admit"}))
        receipt = root / ".build/engineering/admit/source.json"
        receipt.unlink(missing_ok=True)
        with patch.object(cli, "refresh_policy", return_value="policy") as policy, patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stderr(StringIO()) as error:
            result = cli.main(["--project", str(root), "admit", *arguments])
        if policy.called:
            # The policy goes to stderr, leaving stdout to the command.
            self.assertEqual(policy.call_args.args, (root.resolve(), error))
        return result, policy, json.loads(receipt.read_text()) if receipt.exists() else None

    def test_admit_runs_a_command_in_the_current_directory_inside_admission(self):
        work = Path(self.temp.name) / "work"
        work.mkdir()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(work)
        probe = ("from pathlib import Path\nfrom vocaro_engineering import resources\n"
                 "assert resources.inherited()\n"
                 "try: resources.inherited(exclusive=True)\nexcept RuntimeError: held = 'shared'\nelse: held = 'exclusive'\n"
                 "Path('admitted').write_text(held)\nraise SystemExit(7)")
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        for options, held in [([], "shared"), (["--exclusive"], "exclusive")]:
            with self.subTest(held), patch.dict(os.environ, {"PYTHONPATH": str(config.TOOLKIT_ROOT / "src/python")}):
                result, policy, receipt = self.admit(*options, "--", sys.executable, "-c", probe)
                self.assertEqual(result, 7)
                self.assertEqual((work / "admitted").read_text(), held)
                policy.assert_called_once()
                self.assertEqual(receipt["command"], [sys.executable, "-c", probe])
                self.assertEqual((receipt["exitStatus"], receipt["policy"], receipt["exclusive"]), (7, "policy", held == "exclusive"))
                self.assertEqual(Path(receipt["directory"]).resolve(), work.resolve())
                self.assertFalse(guard.exists())
                self.assertIsNone(os.environ.get(resources.TOKEN))

    def test_admit_passes_a_later_separator_to_its_command(self):
        for arguments in [["--", sys.executable, "-c", "pass", "--", "x"], [sys.executable, "-c", "pass", "--", "x"]]:
            with self.subTest(arguments):
                result, _policy, receipt = self.admit(*arguments)
                self.assertEqual(result, 0)
                self.assertEqual(receipt["command"], [sys.executable, "-c", "pass", "--", "x"])

    def test_admit_without_a_command_refreshes_and_admits_nothing(self):
        result, policy, receipt = self.admit("--exclusive")
        self.assertEqual(result, 2)
        policy.assert_not_called()
        self.assertIsNone(receipt)
        self.assertFalse(resources.slot_directory().exists())

    def test_a_command_that_cannot_start_releases_admission(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        unexecutable = Path(self.temp.name) / "check-all.sh"
        unexecutable.write_text("#!/bin/sh\nexit 0\n")
        for command in [str(Path(self.temp.name) / "swfit-typo"), str(unexecutable)]:
            with self.subTest(command):
                # A retained guard would make every later admission wait; fail instead.
                result, _policy, receipt = self.admit("--timeout", "0", "--", command, "test")
                self.assertEqual(result, 2)
                self.assertEqual(receipt["outcome"], "failed-or-interrupted")
                self.assertIn("did not start", receipt["error"])
                self.assertFalse(guard.exists())
                with contextlib.redirect_stderr(StringIO()):
                    with self.assertRaises(processes.NotStarted):
                        resources.main(["--timeout", "0", "--", command])
                self.assertFalse(guard.exists())
                with contextlib.redirect_stderr(StringIO()):
                    with resources.Admission("next", timeout=0): pass


if __name__ == "__main__": unittest.main()
