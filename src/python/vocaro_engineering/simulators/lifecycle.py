"""Explicit simulator ownership. Pool reservations and disposable devices differ.

The owner supplies a reserved pool device; this module never invents that authorization.
A disposable device is created with a unique name and cleaned up by exact identity only.
"""
from contextlib import contextmanager
import json
import subprocess
import uuid


def command(*arguments, timeout=120):
    return subprocess.check_output(["xcrun", "simctl", *arguments], text=True, timeout=timeout).strip()


class Simulator:
    def __init__(self, udid, *, run=command):
        self.udid = str(uuid.UUID(udid))
        self.run = run

    def boot(self):
        self.run("boot", self.udid)
        self.run("bootstatus", self.udid, "-b", timeout=600)

    def install(self, application): self.run("install", self.udid, str(application))
    def launch(self, bundle, *arguments): return self.run("launch", self.udid, bundle, *arguments)
    def screenshot(self, path): self.run("io", self.udid, "screenshot", str(path))


@contextmanager
def disposable(device_type, runtime, *, prefix="VocaroEngineering", run=command):
    name = prefix + "-" + str(uuid.uuid4())
    device = None
    try:
        device = Simulator(run("create", name, device_type, runtime), run=run)
        yield device
    finally:
        if device is None:
            # An interrupted create can leave a device even when no UUID was returned.
            value = json.loads(run("list", "devices", "--json"))
            matches = [item["udid"] for group in value["devices"].values()
                       for item in group if item.get("name") == name]
            if len(matches) > 1: raise RuntimeError("Ambiguous owned simulator creation; inspect it")
            if matches: device = Simulator(matches[0], run=run)
        if device is not None:
            try: run("shutdown", device.udid)
            except subprocess.CalledProcessError: pass  # A created but unbooted device.
            run("delete", device.udid)


def reserved(udid, *, run=command):
    """Use a device already reserved and handed off by project policy. No lifecycle mutation."""
    return Simulator(udid, run=run)
