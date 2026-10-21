import json
from pathlib import Path
import sys
import unittest
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering.simulators.lifecycle import disposable, reserved


class LifecycleTests(unittest.TestCase):
    def test_failure_cleans_up_only_its_created_device(self):
        calls = []
        identifier = str(uuid.uuid4())
        def run(*args, **kwargs):
            calls.append(args)
            if args[0] == "create": return identifier
        with self.assertRaisesRegex(RuntimeError, "work failed"):
            with disposable("type", "runtime", run=run) as device:
                device.boot()
                device.install("app")
                raise RuntimeError("work failed")
        self.assertEqual(calls[-2:], [("shutdown", identifier), ("delete", identifier)])
        self.assertIn(("bootstatus", identifier, "-b"), calls)
        self.assertNotIn("booted", str(calls))

    def test_interrupted_creation_recovers_only_the_unique_name(self):
        own, other = str(uuid.uuid4()), str(uuid.uuid4())
        calls, name = [], None
        def run(*args, **kwargs):
            nonlocal name
            calls.append(args)
            if args[0] == "create":
                name = args[1]
                raise TimeoutError("creation observation timed out")
            if args[0] == "list":
                return json.dumps({"devices": {"runtime": [{"udid": other, "name": "other"},
                                                         {"udid": own, "name": name}]}})
        with self.assertRaises(TimeoutError):
            with disposable("type", "runtime", run=run): pass
        self.assertEqual(calls[-2:], [("shutdown", own), ("delete", own)])
        self.assertNotIn(("delete", other), calls)

    def test_pool_adapter_never_shuts_down_or_deletes_its_device(self):
        calls = []
        device = reserved(str(uuid.uuid4()), run=lambda *args, **kw: calls.append(args))
        device.screenshot("result.png")
        self.assertEqual(calls, [("io", device.udid, "screenshot", "result.png")])
        with self.assertRaises(ValueError): reserved("booted")
