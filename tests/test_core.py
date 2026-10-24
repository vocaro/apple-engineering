import contextlib
from io import StringIO
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
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
            self.assertEqual(config.load(root)["integration"], "direct-main")

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
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example",
                "lanes": {"ui": {"command": ["xcodebuild", "test"], "foreground": "yes"}}}))
            with self.assertRaisesRegex(ValueError, "foreground must be true or false"): config.load(root)

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
                        "integration": "direct-main", "capabilities": capabilities, "lanes": lanes}))
                    with patch.object(cli.shutil, "which", return_value="/usr/bin/true"), patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()) as output:
                        # A warning is not a missing prerequisite.
                        self.assertEqual(cli.main(["--project", directory, "doctor"]), 0)
                    warnings = json.loads(output.getvalue())["warnings"]
                    self.assertEqual(bool(warnings), warned, warnings)
                    for capability in capabilities if warned else []:
                        self.assertIn(capability, warnings[0])

    def test_doctor_warns_when_a_project_declares_no_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            for declared, warned in [({}, True), ({"integration": "direct-main"}, False),
                                     ({"integration": "pull-request"}, False)]:
                with self.subTest(declared=declared):
                    (Path(directory) / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example",
                        **declared}))
                    with patch.object(cli.shutil, "which", return_value="/usr/bin/true"), patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()) as output:
                        self.assertEqual(cli.main(["--project", directory, "doctor"]), 0)
                    warnings = json.loads(output.getvalue())["warnings"]
                    self.assertEqual(bool(warnings), warned, warnings)
                    for warning in warnings:
                        self.assertIn("integration", warning)

    def test_doctor_warns_when_swift_manifests_name_a_toolkit_package_that_does_not_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            # A session worktree, as under .claude/worktrees, with no toolkit beside it.
            worktrees = Path(directory) / "worktrees"
            root = worktrees / "session"
            (root / "app").mkdir(parents=True)
            (root / "App.xcodeproj").mkdir()
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Example",
                "toolkit": {"path": "../apple-engineering"}, "integration": "direct-main"}))
            package = "apple-engineering/src/swift/EngineeringTestSupport"
            (root / "project.yml").write_text(f"packages:\n  EngineeringTestSupport:\n    path: ../{package}\n"
                                              "  Other:\n    path: ../OtherLib\n")
            (root / "App.xcodeproj/project.pbxproj").write_text(f'relativePath = "../{package}";\n')
            (root / "app/project.yml").write_text(f"packages:\n  EngineeringTestSupport:\n    path: ../../{package}\n")
            # An untracked manifest is not the project's.
            (root / "scratch").mkdir()
            (root / "scratch/Package.swift").write_text(f'.package(path: "../../elsewhere/{package}")\n')
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "engineering.json", "project.yml", "app", "App.xcodeproj"],
                           check=True)

            def warnings():
                with patch.object(cli.shutil, "which", return_value="/usr/bin/true"), patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stdout(StringIO()) as output:
                    self.assertEqual(cli.main(["--project", str(root), "doctor"]), 0)
                return json.loads(output.getvalue())["warnings"]

            # doctor resolves the project, and with it the temporary directory's /private prefix.
            link = worktrees.resolve() / "apple-engineering"
            found = warnings()
            # The three manifests name one missing folder, so one link fixes them all.
            self.assertEqual(len(found), 1, found)
            self.assertIn("App.xcodeproj/project.pbxproj, app/project.yml, project.yml name", found[0])
            self.assertIn(f"ln -s {cli.named_checkout(config.TOOLKIT_ROOT)} {link}`", found[0])
            self.assertNotIn("OtherLib", found[0])
            self.assertNotIn("scratch", found[0])
            (link / "src/swift/EngineeringTestSupport").mkdir(parents=True)
            self.assertEqual(warnings(), [])

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
            # Name this checkout even from a worktree, so the launcher runs the toolkit under test.
            with patch.object(cli, "named_checkout", lambda toolkit: toolkit), contextlib.redirect_stdout(StringIO()):
                cli.main(["--project", directory, "init"])
            result = subprocess.run([sys.executable, str(Path(directory) / "scripts/eng"), "instructions"],
                capture_output=True, text=True, env={**os.environ, "PATH": str(Path(sys.executable).parent)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Common engineering rules", result.stdout)
            self.assertEqual((Path(directory) / "CLAUDE.md").read_text(), "@AGENTS.md\n")
            self.assertIn("run `python3 scripts/eng instructions`", (Path(directory) / "AGENTS.md").read_text())


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

    def test_a_lane_that_reports_an_unmeasured_test_or_reaches_its_timeout_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unmeasured = "/p/T.swift:6: -[P.T testA] : Test skipped - Unmeasured: the 80 s backstop passed"
            def lane(output, status=0, **options):
                return {"command": [sys.executable, "-c", f"import sys; print({output!r}); sys.exit({status})"], **options}
            lanes = {"unmeasured": lane(f"{unmeasured}\nRan 2 tests"),
                     "skipped": lane("/p/T.swift:6: -[P.T testA] : Test skipped - needs a Mac\nRan 2 tests"),
                     # A lane that exits 3 itself may not have run every test.
                     "short": lane("Ran 1 test", 3, minimumTests=2),
                     "short-passed": lane("Ran 1 test", minimumTests=2),
                     "failed": lane(f"{unmeasured}\nRan 2 tests", 1),
                     "slow": {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout": 1}}
            (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Lanes", "lanes": lanes}))
            cases = {"unmeasured": (3, "unmeasured"), "skipped": (0, None), "short": (3, "unmeasured"),
                     "short-passed": (2, None), "failed": (1, None), "slow": (3, "unmeasured")}
            for name, (status, outcome) in cases.items():
                with self.subTest(name):
                    with patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stderr(StringIO()) as error:
                        self.assertEqual(cli.main(["--project", directory, "run", name]), status, error.getvalue())
                    recorded = json.loads((root / ".build/engineering" / name / "source.json").read_text())
                    self.assertEqual(recorded.get("outcome"), outcome)
            recorded = json.loads((root / ".build/engineering/unmeasured/source.json").read_text())
            self.assertEqual((recorded["exitStatus"], recorded["unmeasured"]), (0, [unmeasured]))
            self.assertIn("timed out after 1s", json.loads((root / ".build/engineering/slow/source.json").read_text())["error"])
            self.assertIn("Expected at least 2 executed tests; observed 1", self.run_lane(directory, "short"))



class EvidenceTests(unittest.TestCase):
    def test_zero_tests_cannot_pass_but_a_swift_testing_run_is_not_its_zero_test_xctest_shim(self):
        for text in ["** TEST SUCCEEDED **", "Executed 0 tests, with 0 failures", "Ran 0 tests in 0.000s\nOK", "Test run with 0 tests in 0 suites passed"]:
            with self.assertRaises(ValueError): evidence.require_tests(text)
        self.assertEqual(evidence.require_tests("Executed 0 tests, with 0 failures\nTest run with 30 tests in 2 suites passed after 1s"), 30)

        self.assertEqual(evidence.require_tests("Ran 43 tests in 0.5s\n\nOK",43),43)

    def test_a_run_counts_each_bundle_and_swift_testing_run_once(self):
        def xctest(top, bundles):
            """swift test and xcodebuild run each bundle under its own top suite (Xcode 27.1, October 2026)."""
            executed = "\t Executed {} tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds"
            return "".join(f"Test Suite '{top}' started at 2026-10-22 23:11:16.585.\n"
                           f"Test Suite '{name}.xctest' started at 2026-10-22 23:11:16.587.\n"
                           f"Test Suite '{name}Case' passed at 2026-10-22 23:11:16.700.\n{executed.format(count)}\n"
                           f"Test Suite '{name}.xctest' passed at 2026-10-22 23:11:16.744.\n{executed.format(count)}\n"
                           f"Test Suite '{top}' passed at 2026-10-22 23:11:16.744.\n{executed.format(count)}\n"
                           for name, count in bundles)
        swift_testing = "✔ Test run with 65 tests in 5 suites passed after 6.436 seconds.\n"
        whole = xctest("All tests", [("Writing", 42), ("Viewing", 2516), ("Reading", 732)]) + swift_testing + \
            "✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.\n"
        self.assertEqual(evidence.require_tests(whole, 3355, expected=3355), 3355)
        filtered = xctest("Selected tests", [("Writing", 0), ("Viewing", 0), ("Reading", 8)])
        self.assertEqual(evidence.require_tests(filtered, expected=8), 8)
        # A wrapper's total for each simulator counts, but not beside the totals it sums.
        summaries = "Passed: iPhone (iOS 27.0): Executed 3252 tests\nPassed: iPad (iOS 27.0): Executed 3252 tests\n"
        self.assertEqual(evidence.require_tests(summaries, expected=6504), 6504)
        device = xctest("All tests", [("Writing", 16), ("Viewing", 2439), ("Reading", 732)]) + swift_testing
        self.assertEqual(evidence.require_tests(device + summaries.splitlines()[0], expected=3252), 3252)
        self.assertEqual(evidence.require_tests("Ran 40 tests in 1.0s\n\nOK\nRan 3 tests in 0.1s\n\nOK\n", expected=43), 43)

    def test_a_skipped_test_is_not_an_executed_test(self):
        def xctest(count, skipped):
            return ("Test Suite 'All tests' passed at 2026-10-24 09:12:00.000.\n"
                    f"\t Executed {count} tests, with {skipped} tests skipped and 0 failures (0 unexpected) in 0.3 (0.3) seconds\n")
        self.assertEqual(evidence.executed_tests(xctest(6, 6)), 0)
        self.assertEqual(evidence.executed_tests(xctest(6, 2)), 4)
        self.assertEqual(evidence.executed_tests(xctest(1, 1).replace("tests skipped", "test skipped")), 0)
        self.assertEqual(evidence.executed_tests("Ran 4 tests in 0.01s\n\nOK (skipped=4)"), 0)
        self.assertEqual(evidence.executed_tests("Ran 5 tests in 0.01s\n\nFAILED (failures=1, skipped=2)"), 3)
        self.assertEqual(evidence.executed_tests("Ran 40 tests in 0.5s\n\nOK\nRan 3 tests in 0.1s\n\nOK (skipped=1)"), 42)
        # Swift Testing counts a skipped test in its run total; its skip line names it.
        self.assertEqual(evidence.executed_tests('➜ Test foo() skipped: "needs a Mac"\n'
                                                 "✔ Test run with 5 tests in 2 suites passed after 1.0 seconds."), 4)
        self.assertEqual(evidence.executed_tests("➜ Test foo() skipped.\n"
                                                 "✔ Test run with 2 tests in 1 suite passed after 0.1 seconds.\n"
                                                 "✔ Test run with 3 tests in 1 suite passed after 0.1 seconds."), 4)
        # A skipped suite counts a suite, not a test.
        self.assertEqual(evidence.executed_tests("➜ Suite Foo skipped.\n"
                                                 "✔ Test run with 2 tests in 1 suite passed after 0.1 seconds."), 2)
        with self.assertRaisesRegex(ValueError, "at least 1 executed tests; observed 0"):
            evidence.require_tests(xctest(6, 6))

    def test_an_expected_count_must_match_exactly(self):
        self.assertEqual(evidence.require_tests("Executed 0 tests\nTest run with 3 tests in 1 suite passed", expected=3), 3)
        for text in ["Ran 2 tests", "Ran 4 tests", "** TEST SUCCEEDED **"]:
            with self.subTest(text), self.assertRaisesRegex(ValueError, "exactly 3"):
                evidence.require_tests(text, expected=3)

    def test_a_skip_or_cancellation_whose_reason_begins_unmeasured_reports_an_unmeasured_test(self):
        # swift test and xcodebuild print the first two alike, and exit 0; unittest prints its reason
        # only when verbose (Swift 6.4, Xcode 27.1, Python 3.14, October 2026).
        xctest = "/p/Tests/T.swift:6: -[ProbeTests.ProbeXCTests testUnmeasured] : Test skipped - Unmeasured: the 80 s backstop passed"
        swift_testing = '➜ Test swiftTestingUnmeasured() was cancelled after 0.001 seconds: "Unmeasured: the 80 s backstop passed"'
        python = "test_unmeasured (test_probe.Probe.test_unmeasured) ... skipped 'Unmeasured: the 80 s backstop passed'"
        measured = ["/p/Tests/T.swift:9: -[ProbeTests.ProbeXCTests testOther] : Test skipped - needs a Mac",
                    "Test Case '-[ProbeTests.ProbeXCTests testUnmeasured]' skipped (0.002 seconds).",
                    '➜ Test other() was cancelled after 0.001 seconds: "the window closed"',
                    "test_other (test_probe.Probe.test_other) ... skipped 'needs a Mac'",
                    "Unmeasured: macOS: 1 tests a busy host decided; see mac.log"]
        # A wrapper's summary that repeats a line adds no test.
        log = "\n".join([*measured, xctest, swift_testing, python, xctest]) + "\n"
        self.assertEqual(evidence.unmeasured_tests(log), [xctest, swift_testing, python])
        self.assertEqual(evidence.unmeasured_tests("\n".join(measured)), [])

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

    def test_a_fragment_must_name_a_heading_or_anchor_of_its_markdown_target(self):
        target = ("# Target\n\n## Repeated\n\n## Repeated\n\n## The `eng docs` check — 0.3.1\n\n"
                  "## [Linked](elsewhere.md) __init__ and C#\n\n"
                  '<a id="stacks"></a>\n\nSetext title\n------------\n\n- a list item\n---\n\n'
                  "```sh\n# not a heading\n```\n")
        links = ("[a](target.md#repeated) [b](target.md#repeated-1) [c](target.md#the-eng-docs-check--031)\n"
                 "[d](target.md#linked-init-and-c) [e](target.md#stacks) [f](target.md#setext-title)\n"
                 "[g](#local) [h](notes.txt#L3) [i](target.md)\n\n## Local\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "target.md").write_text(target)
            (root / "notes.txt").write_text("a\nb\nc\n")
            (root / "README.md").write_text(links)
            self.assertEqual(docs.check(root, ["README.md"]), [])
            # Renaming a heading strands the links to its old anchor.
            (root / "target.md").write_text(target.replace("Setext title", "Setext heading"))
            (root / "README.md").write_text(links + "[j](target.md#repeated-2) [k](target.md#not-a-heading)\n"
                                            "[l](target.md#a-list-item) [m](#nowhere)\n")
            self.assertEqual(docs.check(root, ["README.md"]), [
                f"{root / 'README.md'}: missing anchor: target.md#setext-title",
                f"{root / 'README.md'}: missing anchor: target.md#repeated-2",
                f"{root / 'README.md'}: missing anchor: target.md#not-a-heading",
                f"{root / 'README.md'}: missing anchor: target.md#a-list-item",
                f"{root / 'README.md'}: missing anchor: #nowhere"])

    def test_heading_slugs_follow_github(self):
        for heading, expected in [("Concurrent Git integration", "concurrent-git-integration"),
                                  ("0.3.1 release verification", "031-release-verification"),
                                  ("A — B", "a--b"), ("foo_bar & `x.y`", "foo_bar--xy"),
                                  ("Ünïcode café", "ünïcode-café"), ("**Bold** *it*", "bold-it")]:
            with self.subTest(heading):
                self.assertEqual(docs.slug(docs.heading_text(heading)), expected)

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

    def test_the_project_adapter_reuses_heavy_or_exclusive_admission_only_in_its_namespace(self):
        adapter = config.TOOLKIT_ROOT / "integrations/shared.py"
        lock = os.environ["SW_GATE_LOCK_FILE"]
        # Read at each call: an admission adds its token to the environment.
        environment = lambda: {**os.environ, "VOCARO_ENGINEERING_ROOT": str(config.TOOLKIT_ROOT)}
        def verify(namespace, descriptors=()):
            return subprocess.run([sys.executable, str(adapter), "--verify-admission", namespace],
                                  env=environment(), pass_fds=descriptors).returncode
        for exclusive in [False, True]:
            with self.subTest(exclusive=exclusive), resources.Admission("gate", exclusive=exclusive, timeout=0):
                descriptors = tuple(item["fd"] for item in json.loads(os.environ[resources.TOKEN])["locks"])
                self.assertEqual(verify(lock, descriptors), 0)
                self.assertEqual(verify(lock + "-fixture", descriptors), 1)
        self.assertEqual(verify(lock), 1)
        admitted = subprocess.run([sys.executable, str(adapter), "--admit", "0", "--", sys.executable, "-c",
                                   f"import os; print('{resources.TOKEN}' in os.environ)"],
                                  env=environment(), capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stderr)
        self.assertEqual(admitted.stdout.strip(), "True")

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

    def test_a_stop_signal_ends_the_command_then_releases_admission(self):
        # An agent's task stop sent eng admit SIGTERM, which ended it without leaving admission
        # while its command ran on in its own session (2026-10-22).
        root = Path(self.temp.name)
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        marker = root / "command.pid"
        command = [sys.executable, "-c", f"import os, pathlib, time\npathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(120)"]
        (root / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Stop",
            "lanes": {"stopped": {"command": command, "resource": "heavy"}}}))
        launch = ("import sys\nfrom unittest.mock import patch\nfrom vocaro_engineering import cli\n"
                  "with patch.object(cli, 'refresh_policy', return_value='policy'), patch.object(cli, 'source_identity', return_value={}):\n"
                  "    raise SystemExit(cli.main(sys.argv[1:]))\n")
        entries = {"resources": [sys.executable, "-m", "vocaro_engineering.resources", "--", *command],
                   "admit": [sys.executable, "-c", launch, "--project", str(root), "admit", "--", *command],
                   "run": [sys.executable, "-c", launch, "--project", str(root), "run", "stopped"]}
        cases = [(entry, signal.SIGTERM) for entry in entries] + [("resources", signal.SIGHUP), ("resources", signal.SIGINT)]
        environment = {**os.environ, "PYTHONPATH": str(config.TOOLKIT_ROOT / "src/python")}
        for entry, number in cases:
            with self.subTest(entry=entry, signal=number.name):
                guard.unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
                # SIGINT as a terminal's foreground job has it, which a background job ignores.
                admitted = subprocess.Popen(entries[entry], cwd=root, env=environment, stderr=subprocess.DEVNULL,
                                            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
                pid = birth = None
                try:
                    deadline = time.monotonic() + 30
                    while not (marker.exists() and marker.read_text()):
                        self.assertIsNone(admitted.poll(), "the command was never started")
                        self.assertLess(time.monotonic(), deadline, "the command was never started")
                        time.sleep(0.01)
                    pid = int(marker.read_text())
                    birth = resources.process_start(pid)
                    os.kill(admitted.pid, number)
                    self.assertEqual(admitted.wait(timeout=30), -number)
                    self.assertNotEqual(resources.process_start(pid), birth, "the command outlived its stop")
                    self.assertFalse(guard.exists())
                    if entry != "resources":
                        receipts = {"admit": "admit", "run": "stopped"}
                        receipt = json.loads((root / ".build/engineering" / receipts[entry] / "source.json").read_text())
                        self.assertEqual(receipt["outcome"], "failed-or-interrupted")
                        self.assertIn(f"Stopped by {number.name} after its command", receipt["error"])
                finally:
                    if admitted.poll() is None:
                        admitted.kill()
                        admitted.wait()
                    if pid is not None and resources.process_start(pid) == birth:
                        os.kill(pid, signal.SIGKILL)

    def test_a_task_stop_beside_a_finishing_job_strands_neither_entry(self):
        # A task stop signaled one job's whole process tree while another job ran beside it (#15,
        # 2026-10-22). The stopped job's entry died with its admitting process, and the job beside
        # it, finishing normally while that entry stood, left its own: two dead entries refused
        # every session's heavy work until attended recovery.
        root = Path(self.temp.name)
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        marker = root / "command.pids"
        # The command ends on SIGTERM, as the lane's script did, and has a child in its own session.
        command = [sys.executable, "-c", "import os, pathlib, subprocess, sys, time\n"
                   "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
                   f"pathlib.Path({str(marker)!r}).write_text(f'{{os.getpid()}} {{child.pid}}')\ntime.sleep(120)"]
        environment = {**os.environ, "PYTHONPATH": str(config.TOOLKIT_ROOT / "src/python")}
        stopped = subprocess.Popen([sys.executable, "-m", "vocaro_engineering.resources", "--", *command],
                                   cwd=root, env=environment, stderr=subprocess.DEVNULL)
        tree = {}
        try:
            deadline = time.monotonic() + 30
            while not (marker.exists() and len(marker.read_text().split()) == 2):
                self.assertIsNone(stopped.poll(), "the command was never started")
                self.assertLess(time.monotonic(), deadline, "the command was never started")
                time.sleep(0.01)
            with contextlib.redirect_stderr(StringIO()), resources.Admission("beside", timeout=0):
                # Claude Code's TaskStop sends SIGTERM to every process descended from the task.
                current, pending = processes.snapshot(), [stopped.pid]
                while pending:
                    pid = pending.pop()
                    tree[pid] = current[pid][2]
                    pending.extend(child for child, (parent, _group, _birth) in current.items() if parent == pid)
                self.assertLessEqual({int(pid) for pid in marker.read_text().split()}, tree.keys())
                for pid in tree:
                    with contextlib.suppress(ProcessLookupError): os.kill(pid, signal.SIGTERM)
                self.assertEqual(stopped.wait(timeout=30), -signal.SIGTERM)
            survivors = [pid for pid, (_parent, _group, birth) in processes.snapshot().items() if tree.get(pid) == birth]
            self.assertEqual(survivors, [])
            self.assertFalse(guard.exists())
            with contextlib.redirect_stderr(StringIO()), resources.Admission("next", timeout=0): pass
        finally:
            if stopped.poll() is None:
                stopped.kill()
                stopped.wait()
            for pid, (_parent, _group, birth) in processes.snapshot().items():
                if tree.get(pid) == birth:
                    with contextlib.suppress(ProcessLookupError): os.kill(pid, signal.SIGKILL)

    def test_a_stop_that_cannot_confirm_every_process_ended_leaves_the_entry_uncertain(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        real, roots, marked = processes.snapshot, [], []
        # Above macOS's PID limit, so no signal reaches a real process: it never ends.
        phantom = 99999999
        def observed():
            current = real()
            if not roots:
                roots.extend(pid for pid, (parent, group, _birth) in current.items() if parent == os.getpid() and group == pid)
                if roots: processes.request_stop(signal.SIGTERM)
            elif guard.exists():
                marked.append(json.loads(guard.read_text())["owners"][admission.identity].get("uncertain"))
            if roots: current[phantom] = (roots[0], phantom, "phantom")
            return current
        self.addCleanup(processes._stops.clear)
        with patch.object(processes, "snapshot", observed), patch.object(processes, "KILL_AFTER", 0.1), \
             patch.object(processes, "KILL_WAIT", 0.2), contextlib.redirect_stderr(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "SIGTERM, but owned descendants have no confirmed terminal result"):
                with resources.Admission("stopped", timeout=0) as admission:
                    processes.supervise([sys.executable, "-c", "import time; time.sleep(30)"], cwd=self.temp.name,
                                        on_stop=admission.interrupted)
        # Marked while the stop drained, in case SIGKILL had ended this process first.
        self.assertTrue(marked and all(marked))
        self.assertTrue(json.loads(guard.read_text())["owners"][admission.identity]["uncertain"])

    def test_a_timed_out_run_releases_admission_once_its_command_ended(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        with contextlib.redirect_stderr(StringIO()), self.assertRaises(processes.TimedOut):
            with resources.Admission("timed out", timeout=0):
                processes.supervise([sys.executable, "-c", "import time; time.sleep(30)"], cwd=self.temp.name, timeout=0.2)
        self.assertFalse(guard.exists())
        with contextlib.redirect_stderr(StringIO()), resources.Admission("next", timeout=0): pass

    def test_a_timeout_that_cannot_confirm_every_process_ended_leaves_the_entry_uncertain(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        real, roots = processes.snapshot, []
        # Above macOS's PID limit, so no signal reaches a real process: it never ends.
        phantom = 99999999
        def observed():
            current = real()
            if not roots:
                roots.extend(pid for pid, (parent, group, _birth) in current.items() if parent == os.getpid() and group == pid)
            if roots: current[phantom] = (roots[0], phantom, "phantom")
            return current
        with patch.object(processes, "snapshot", observed), patch.object(processes, "KILL_AFTER", 0.1), \
             patch.object(processes, "KILL_WAIT", 0.2), contextlib.redirect_stderr(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Timed out after 0.2s, but owned descendants have no confirmed terminal result"):
                with resources.Admission("timed out", timeout=0) as admission:
                    processes.supervise([sys.executable, "-c", "import time; time.sleep(30)"], cwd=self.temp.name, timeout=0.2)
        self.assertTrue(json.loads(guard.read_text())["owners"][admission.identity]["uncertain"])

    def test_a_stop_before_the_command_starts_leaves_no_entry(self):
        guard = Path(os.environ["SW_GATE_LOCK_FILE"] + ".warm-push-guard")
        self.addCleanup(processes._stops.clear)
        processes.request_stop(signal.SIGTERM)
        with self.subTest("admitted"), contextlib.redirect_stderr(StringIO()):
            with self.assertRaisesRegex(processes.Interrupted, "before its command started"):
                with resources.Admission("admitted", timeout=0) as admission:
                    processes.supervise([sys.executable, "-c", "pass"], cwd=self.temp.name, on_stop=admission.interrupted)
            self.assertFalse(guard.exists())
        with self.subTest("queued"), contextlib.redirect_stderr(StringIO()):
            self.hold(0, 1, 2)
            # Without the stop this waits the whole minute and then times out.
            with self.assertRaisesRegex(processes.Interrupted, "while waiting for admission"):
                with resources.Admission("queued", timeout=60): self.fail("admitted")
            self.assertFalse(guard.exists())

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
