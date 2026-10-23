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
from vocaro_engineering import cli, config, spelling


def git(cwd, *arguments):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(cwd), *arguments], check=True, capture_output=True, env=environment)


class Project(unittest.TestCase):
    """A throwaway repository whose tracked files are the given text."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.root)])
        git(self.root, "init", "-q")

    def write(self, files, spelling=None, track=True):
        value = {"schemaVersion": 1, "name": "Example"}
        if spelling is not None:
            value["spelling"] = spelling
        files = {"engineering.json": json.dumps(value), **files}
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text) if isinstance(text, str) else path.write_bytes(text)
        if track:
            git(self.root, "add", *files)

    def check(self, *paths):
        lines = []
        status = spelling.check(self.root, config.load(self.root), paths, out=lines.append)
        return status, lines


class DetectionTests(Project):
    def test_the_built_in_controls_hold(self):
        self.assertEqual(spelling.controls(), [])

    def test_identifiers_comments_and_documents_each_fail(self):
        self.write({"Sources/Ramp.swift": "struct Ramp {\n    let colourRamp: [Int]\n}\n",
                    "tool.py": "def f():\n    # centre the label\n    return KIND_LABELLED_RASTER\n",
                    "doc/guide.md": "# Guide\n\nThe licence travels with the book.\n"})
        status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertIn("Sources/Ramp.swift:2: British spelling 'colour' -> color", lines)
        self.assertIn("tool.py:2: British spelling 'centre' -> center", lines)
        self.assertIn("tool.py:3: British spelling 'LABELLED' -> labeled", lines)
        self.assertIn("doc/guide.md:3: British spelling 'licence' -> license", lines)
        self.assertTrue(lines[-1].startswith(
            "eng spelling: FAIL — 4 British spelling(s) in 4 text file(s) and 6 file name(s)"))

    def test_american_text_and_names_others_chose_pass(self):
        self.write({"Sources/Unit.swift": "// Unity's MonoBehaviour; Apple's Task.isCancelled\n"
                                          "if Task.isCancelled { return .canceled }\n"
                                          "let gray = QuiescentRegionCount.center\n",
                    "README.md": "Toward the harbor, see https://example.com/colour-grading.\n"
                                 "<li><em>The Colour of Magic</em>, a cited title. Its color is ours.</li>\n",
                    "Decode.swift": 'case "cancelled": self = .canceled  // spelling: keep, stored by 1.0\n',
                    "Escaped.py": 'print("done\\nraise")\n',
                    "logo.png": b"\x89PNG\r\n\x1a\n\0colour"})
        status, lines = self.check()
        self.assertEqual(status, 0, lines)
        self.assertTrue(lines[-1].startswith("eng spelling: PASS — 5 text file(s) and 7 file name(s)"))

    def test_file_and_directory_names_each_fail(self):
        self.write({"Docs/colour-chart.png": b"\x89PNG\r\n\x1a\n\0",
                    "centre/README.md": "# Center\n", "centre/notes.md": "Notes.\n",
                    "Tests/NeighbourAlignmentTests.swift": "final class AlignmentTests {}\n",
                    "fixtures/grey_ramp.json": "[]\n"})
        status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertEqual(lines[:-1], [
            "Docs/colour-chart.png: British spelling in file name 'colour' -> color",
            "Tests/NeighbourAlignmentTests.swift: British spelling in file name 'Neighbour' -> neighbor",
            "centre/: British spelling in file name 'centre' -> center",
            "fixtures/grey_ramp.json: British spelling in file name 'grey' -> gray"])
        self.assertTrue(lines[-1].startswith(
            "eng spelling: FAIL — 4 British spelling(s) in 5 text file(s) and 10 file name(s)"))

    def test_names_others_chose_pass(self):
        self.write({"LICENCE": "MIT\n", "Unity/MonoBehaviour.cs": "class Tool {}\n",
                    "Sources/QuiescentRegionCount.swift": "let count = 0\n",
                    "credits/Mould.md": "A name.\n", "png/colour type.md": "The field.\n",
                    "Unity/EditorBehaviourHook.cs": "class Hook {}\n"},
                   spelling={"exemptTokens": {"Mould": "a proper name"},
                             "exemptPhrases": {"colour type": "the PNG specification's field name"},
                             "exemptRuns": {"EditorBehaviourHook": "a third-party API"}})
        status, lines = self.check()
        self.assertEqual(status, 0, lines)

    def test_a_cited_title_exempts_only_its_first_emphasis(self):
        self.write({"refs.html": "<li><em>Colour</em> and <em>Colour</em></li>\n"})
        self.assertEqual(self.check()[0], 1)

    def test_a_keep_marker_needs_a_reason(self):
        self.write({"a.py": "x = 'cancelled'  # spelling: keep\n"})
        self.assertEqual(self.check()[0], 1)


class ExemptionTests(Project):
    def test_a_project_names_its_own_exemptions_with_reasons(self):
        self.write({"doc/papers/source.txt": "The colour of the sea.\n",
                    "png.py": "# Read the PNG colour type byte.\n",
                    "credits.md": "Steve Mould's video. Mould is a name.\n",
                    "Unity.cs": "class Tool : EditorBehaviourHook {}\n"},
                   spelling={"skip": {"doc/papers/": "third-party papers, kept verbatim"},
                             "exemptPhrases": {"colour type": "the PNG specification's field name"},
                             "exemptTokens": {"Mould": "a proper name"},
                             "exemptRuns": {"EditorBehaviourHook": "a third-party API"}})
        status, lines = self.check()
        self.assertEqual(status, 0, lines)

    def test_an_exemption_covers_only_what_it_names(self):
        self.write({"notes.md": "Mould the colour. A mould grows.\n"},
                   spelling={"exemptTokens": {"Mould": "a proper name"}})
        status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertEqual([l.split(": ", 1)[1] for l in lines[:-1]],
                         ["British spelling 'colour' -> color", "British spelling 'mould' -> mold"])

    def test_a_skip_exempts_the_skipped_paths_names_but_not_the_directories_above(self):
        self.write({"centre/colour-papers/grey.pdf": b"%PDF\0", "upstream/Behaviour.txt": "Kept.\n",
                    "README.md": "Read centre/colour-papers/ and upstream/Behaviour.txt in colour.\n"},
                   spelling={"skip": {"centre/colour-papers/": "third-party papers, kept verbatim",
                                      "upstream/Behaviour.txt": "retained upstream text"}})
        status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertEqual(lines[:-1], ["centre/: British spelling in file name 'centre' -> center",
                                      "README.md:1: British spelling 'colour' -> color"])

    def test_an_exemption_without_a_reason_is_rejected(self):
        for value in [{"exemptTokens": {"Mould": ""}}, {"exemptTokens": ["Mould"]}, {"allow": {}}]:
            self.write({}, spelling=value)
            with self.assertRaises(ValueError):
                config.load(self.root)


class ControlTests(Project):
    def test_a_detector_that_stopped_detecting_fails_before_reading_files(self):
        self.write({"a.md": "colour\n"})
        with patch.object(spelling, "american_for", return_value=None):
            status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertIn("eng spelling: CONTROL FAILED — 'colour' was not flagged", lines)
        self.assertNotIn("a.md", "\n".join(lines))

    def test_a_detector_that_flags_american_words_fails(self):
        self.write({"a.md": "color\n"})
        with patch.object(spelling, "american_for", return_value="x"):
            status, lines = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any("was flagged" in line for line in lines))

    def test_a_name_check_that_stopped_detecting_fails_before_reading_files(self):
        self.write({"colour.md": "colour\n"})
        for broken in [patch.object(spelling, "british_names", return_value=[]),
                       patch.object(spelling, "names_of", lambda paths, rules: list(paths))]:
            with broken:
                status, lines = self.check()
            self.assertEqual(status, 1)
            self.assertIn("eng spelling: CONTROL FAILED — file name 'centre/README.md' was not flagged",
                          lines)
            self.assertNotIn("colour.md", "\n".join(lines))
            self.assertNotIn("CONTROL FAILED — '", "\n".join(lines))   # the word controls held

    def test_a_name_check_that_flags_american_names_fails(self):
        with patch.object(spelling, "names_of", lambda paths, rules: ["licence"]):
            failures = spelling.controls()
        self.assertIn("file name 'LICENCE' was flagged as [('licence', 'licence', 'license')]", failures)


class ScopeTests(Project):
    def test_named_paths_also_read_untracked_files_git_does_not_ignore(self):
        self.write({".gitignore": "build/\n"})
        self.write({"site/page.html": "<p>centred</p>\n", "site/build/out.html": "<p>centred</p>\n"},
                   track=False)
        self.assertEqual(self.check()[0], 0)        # untracked: no push carries them
        status, lines = self.check(str(self.root / "site"))
        self.assertEqual(status, 1)
        self.assertIn("site/page.html:1: British spelling 'centred' -> centered", lines)
        self.assertNotIn("site/build/out.html", "\n".join(lines))

    def test_named_paths_also_judge_untracked_names(self):
        self.write({".gitignore": "build/\n", "site/index.html": "<p>Home</p>\n"})
        self.write({"site/colour.png": b"\x89PNG\0", "site/build/centre.html": "<p>Out</p>\n"}, track=False)
        self.assertEqual(self.check()[0], 0)        # untracked: no push carries them
        status, lines = self.check(str(self.root / "site"))
        self.assertEqual(status, 1)
        self.assertEqual(lines[:-1], ["site/colour.png: British spelling in file name 'colour' -> color"])

    def test_a_named_path_of_binary_files_still_judges_their_names(self):
        self.write({"assets/color.png": b"\x89PNG\0"})
        self.assertEqual(self.check(str(self.root / "assets"))[0], 0)
        self.write({"assets/colour.png": b"\x89PNG\0"})
        self.assertEqual(self.check(str(self.root / "assets"))[0], 1)

    def test_a_run_that_checked_nothing_is_not_a_pass(self):
        self.write({"a.md": "color\n"})
        self.assertEqual(self.check(str(self.root / "missing"))[0], 2)
        self.assertEqual(self.check(str(self.root.parent))[0], 2)
        subprocess.run(["rm", "-rf", str(self.root / ".git")], check=True)
        self.assertEqual(self.check()[0], 2)

    def test_the_command_line_reports_the_exit_status(self):
        self.write({"a.md": "The colour.\n"})
        with contextlib.redirect_stdout(StringIO()) as output:
            self.assertEqual(cli.main(["--project", str(self.root), "spelling"]), 1)
        self.assertIn("a.md:1: British spelling 'colour' -> color", output.getvalue())
        self.write({"a.md": "The color.\n"})
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(cli.main(["--project", str(self.root), "spelling"]), 0)


class RepositoryTests(unittest.TestCase):
    def test_this_repository_is_spelled_the_american_way(self):
        root = Path(__file__).resolve().parents[1]
        lines = []
        self.assertEqual(spelling.check(root, config.load(root), out=lines.append), 0, "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
