import contextlib
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import cli, config, docs, evidence, resources


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



class EvidenceTests(unittest.TestCase):
    def test_zero_tests_cannot_pass_but_a_swift_testing_run_is_not_its_zero_test_xctest_shim(self):
        for text in ["** TEST SUCCEEDED **", "Executed 0 tests, with 0 failures", "Ran 0 tests in 0.000s\nOK", "Test run with 0 tests in 0 suites passed"]:
            with self.assertRaises(ValueError): evidence.require_tests(text)
        self.assertEqual(evidence.require_tests("Executed 0 tests, with 0 failures\nTest run with 30 tests in 2 suites passed after 1s"), 30)

        self.assertEqual(evidence.require_tests("Ran 43 tests in 0.5s\n\nOK",43),43)

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
        self.assertEqual([e["id"] for e in value["entries"]], list(range(1, 58)))
        for entry in value["entries"]:
            self.assertTrue((config.TOOLKIT_ROOT / entry["path"]).is_file())
            self.assertTrue(entry["sources"], entry["title"])


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


if __name__ == "__main__": unittest.main()
