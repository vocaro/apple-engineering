import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/python/vocaro_engineering/reader_evidence.py"
LOG = ("runner diagnostics\nREADER VIEWPORT Book: 0xabc\nREADER CAPTURE ROOT /Users/private/Devices/ID\n"
       "APP STATE open: 0xdef\n  continued\nAPP ROOT /Users/private/elsewhere\nTest Case 'probe' passed.\n")


def adapter(**settings):
    """The module as a project adapter loads it, with the adapter's settings defined first."""
    namespace = {"__name__": "_reader_evidence_under_test", **settings}
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), namespace)
    return namespace


class ReaderEvidenceSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / "run"
        attachments = self.root / "run-attachments"
        attachments.mkdir()
        (attachments / "kept.txt").write_text("Synthetic")
        (attachments / "manifest.json").write_text(json.dumps([{"testIdentifier": "Tests/testRun()", "attachments": [
            {"exportedFileName": "kept.txt", "suggestedHumanReadableName": "Shown state"}]}]))
        for name in ("summary", "tests"):
            (self.root / f"run-{name}.json").write_text("{}")
        (self.root / "run.log").write_text(LOG)

    def host(self, host):
        (self.root / "run-revision.json").write_text(json.dumps({"host": host}))

    def retain(self, module, profile, name, **arguments):
        destination = self.root / name
        with contextlib.redirect_stdout(StringIO()):
            module["retain"](self.prefix, destination, profile, **arguments)
        return destination

    def test_the_adapter_supplies_its_own_profiles_and_log_marker(self):
        module = adapter(PROFILES={"device-free": ("Shown",), "share-simulator": ("Shown",)},
                         SIMULATOR_PROFILES=("device-free",), LOG_MARKER="APP", PRIVATE_LOG_LINES=("APP ROOT ",))
        self.host("physical iPad")
        with self.assertRaisesRegex(ValueError, "device-free requires an explicit simulator host receipt"):
            self.retain(module, "device-free", "refused")
        self.assertFalse((self.root / "refused").exists())
        # Another product's profile names and marker are not built in.
        retained = self.retain(module, "share-simulator", "physical")
        self.assertEqual((retained / "spoken-output.log").read_text(),
                         "APP STATE open: <address>\n  continued\nTest Case 'probe' passed.\n")
        self.host("disposable iPad simulator")
        self.assertTrue((self.retain(module, "device-free", "simulator") / "manifest.json").is_file())

    def test_arguments_override_the_adapter_settings(self):
        module = adapter(PROFILES={"any": ("Shown",)}, SIMULATOR_PROFILES=(), LOG_MARKER="APP")
        self.host("physical iPad")
        with self.assertRaises(ValueError):
            self.retain(module, "any", "refused", simulator_profiles=("any",))
        self.assertEqual(module["reader_log"](LOG, "READER", ("READER CAPTURE ROOT ",)),
                         "READER VIEWPORT Book: <address>\nTest Case 'probe' passed.\n")
        self.assertIn("APP ROOT", module["reader_log"](LOG))

    def test_without_a_log_marker_nothing_from_the_log_is_published(self):
        module = adapter(PROFILES={"any": ("Shown",)}, SIMULATOR_PROFILES=())
        self.host("physical iPad")
        with self.assertRaisesRegex(ValueError, "LOG_MARKER"):
            self.retain(module, "any", "unmarked")
        self.assertFalse((self.root / "unmarked").exists())
        with self.assertRaisesRegex(ValueError, "LOG_MARKER"):
            module["reader_log"](LOG, "")

    def test_an_adapter_with_only_profiles_gets_no_product_defaults(self):
        # Pagepour's names once were the module's own; an adapter now has to supply its settings.
        module = adapter(PROFILES={"share-simulator": ("Shown",), "mobile-windows": ("Shown",)})
        self.assertEqual((module["SIMULATOR_PROFILES"], module["LOG_MARKER"], module["PRIVATE_LOG_LINES"]),
                         (None, None, None))
        self.host("physical iPhone")
        with self.assertRaisesRegex(ValueError, "LOG_MARKER"):
            self.retain(module, "share-simulator", "unconfigured")
        self.assertFalse((self.root / "unconfigured").exists())
        with self.assertRaisesRegex(ValueError, "LOG_MARKER"):
            module["reader_log"](LOG)


if __name__ == "__main__":
    unittest.main()
