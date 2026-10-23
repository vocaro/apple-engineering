import contextlib
from datetime import datetime, timedelta, timezone
import fcntl
from io import StringIO
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "src/python"
sys.path.insert(0, str(SOURCE))
from vocaro_engineering import cli, devices

# Well-formed, invented identifiers: a hardware UDID and a simulator UUID.
PHONE = "00008130-001A2C3E0C38001C"
DUO = "5B0E6C51-2D3A-4F7B-9C1E-0A4B8D2F6E13"

WRITER = r"""
import contextlib, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from vocaro_engineering import devices
path, key, ready, count, mode, release_by = sys.argv[2:8]
record = devices.Record(path)
if mode == "unlocked":
    record._exclusive = contextlib.nullcontext
load = record.load
def composing():
    value = load()
    time.sleep(0.3)
    return value
record.load = composing
Path(ready, key).touch()
while len(list(Path(ready).iterdir())) < int(count):
    time.sleep(0.005)
record.reserve(key, owner=key, revision=0, purpose="concurrent claim", release_by=release_by)
"""


def later(minutes=30):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def approval(**changes):
    """The owner's approval of a foreground window: given a minute ago, for the next hour."""
    return {"by": "owner", "at": later(-1), "until": later(60), **changes}


class Later(datetime):
    """Two hours from now, for a deadline or an approval that has passed."""

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + timedelta(hours=2)


def scratch():
    """A test directory outside /private/tmp, which the record refuses, even when TMPDIR is there."""
    base = Path(tempfile.gettempdir())
    if devices.restart_emptied(base):
        if sys.platform == "darwin":
            base = Path(subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True).strip())
        else:
            base = Path(__file__).resolve().parents[1] / ".build"
            base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


class DeviceRecordTests(unittest.TestCase):
    def setUp(self):
        temp = scratch()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "device-handoff.json"
        self.record = devices.Record(self.path)
        for patcher in (patch.dict(os.environ, {devices.OVERRIDE: str(self.path)}),
                        patch.object(devices, "LEGACY", str(self.root / "legacy-*device-handoff*.json"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        # Run as on the owner's Mac, whatever runs the tests.
        for name in ("RUNNER_ENVIRONMENT", devices.OWNER):
            os.environ.pop(name, None)

    def reserve(self, key="iPhone", owner="session-a", revision=0, **options):
        return self.record.reserve(key, owner=owner, revision=revision, purpose="bounded UI test",
                                   release_by=options.pop("release_by", later()), **options)

    def foreground(self, owner="session-a", revision=0, **options):
        return self.record.reserve(devices.FOREGROUND, owner=owner, revision=revision, purpose="attended Mac XCUITest",
                                   release_by=options.pop("release_by", later()),
                                   approval=options.pop("approval", approval()), **options)

    def cli(self, *arguments):
        with contextlib.redirect_stdout(StringIO()) as output, contextlib.redirect_stderr(StringIO()) as error:
            code = devices.main(list(arguments))
        return code, output.getvalue(), error.getvalue()

    def legacy(self, name, value):
        path = self.root / f"legacy-{name}-device-handoff.json"
        path.write_text(json.dumps(value, indent=2))
        return path

    def test_the_default_record_survives_a_restart_and_ignores_a_session_home_or_tmpdir(self):
        account = Path(pwd.getpwuid(os.getuid()).pw_dir)
        with patch.dict(os.environ, {"HOME": str(self.root), "TMPDIR": str(self.root)}):
            del os.environ[devices.OVERRIDE]
            chosen = devices.record_path()
        base = "Library/Application Support" if sys.platform == "darwin" else ".local/state"
        self.assertEqual(chosen, account / base / "vocaro-engineering/device-handoff.json")
        self.assertFalse(devices.restart_emptied(chosen))
        temporary = [Path(tempfile.gettempdir()).resolve()]
        if sys.platform == "darwin":
            temporary.append(Path(subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True).strip()).resolve())
        for directory in temporary:
            self.assertNotIn(directory, chosen.resolve().parents)

    def test_locations_a_restart_empties_are_refused(self):
        for path in ["/private/tmp/shared-device-handoff.json", "/tmp/pagepour-studywright-device-handoff.json"]:
            with self.subTest(path):
                with self.assertRaisesRegex(ValueError, "emptied by a restart"):
                    devices.Record(path)
                with patch.dict(os.environ, {devices.OVERRIDE: path}):
                    code, _output, error = self.cli("status")
                self.assertEqual(code, 2)
                self.assertIn("emptied by a restart", error)
        self.assertEqual(devices.Record().path, self.path)

    def concurrent_claims(self, mode, count=4):
        ready = self.root / f"ready-{mode}"
        ready.mkdir()
        path = self.root / f"{mode}.json"
        writers = [subprocess.Popen([sys.executable, "-c", WRITER, str(SOURCE), str(path), f"device-{index}",
                                     str(ready), str(count), mode, later()], stderr=subprocess.PIPE, text=True)
                   for index in range(count)]
        errors = [writer.communicate(timeout=60)[1] for writer in writers]
        self.assertEqual([writer.returncode for writer in writers], [0] * count, errors)
        return devices.Record(path).load()

    def test_concurrent_writers_keep_every_entry_and_without_the_lock_lose_some(self):
        record = self.concurrent_claims("locked")
        self.assertEqual(sorted(record["devices"]), [f"device-{index}" for index in range(4)])
        self.assertEqual(record["revision"], 4)
        # Negative control: the same claims without the lock overwrite each other, so a loss is visible.
        self.assertLess(len(self.concurrent_claims("unlocked")["devices"]), 4)

    def test_a_stale_revision_or_another_owner_changes_nothing(self):
        peer = self.reserve("iPad", owner="session-b")
        first = self.reserve(device=PHONE)
        second = self.record.update("iPhone", owner="session-a", revision=first["revision"], run="smallest case")
        before = self.path.read_bytes()
        with self.assertRaises(devices.Stale):
            self.record.update("iPhone", owner="session-a", revision=first["revision"], run="stale read")
        with self.assertRaises(devices.Stale):
            self.reserve(owner="session-c", revision=0)
        with self.assertRaisesRegex(devices.Refused, "not held by session-b"):
            self.record.update("iPhone", owner="session-b", revision=second["revision"], run="taken")
        with self.assertRaisesRegex(devices.Refused, "held by session-a"):
            self.reserve(owner="session-b", revision=second["revision"])
        with self.assertRaisesRegex(ValueError, "ownerChatID"):
            self.record.update("iPhone", owner="session-a", revision=second["revision"], ownerChatID="session-b")
        self.assertEqual(self.path.read_bytes(), before)
        third = self.record.update("iPhone", owner="session-a", revision=second["revision"], run="current read")
        self.assertEqual(third["revision"], second["revision"] + 1)
        self.assertEqual(self.record.entry("iPad"), peer)

    def test_a_passed_deadline_releases_nothing(self):
        entry = self.reserve()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        entry = self.record.update("iPhone", owner="session-a", revision=entry["revision"], expectedReleaseBy=past)
        self.assertEqual(devices.condition(entry), "held")
        with self.assertRaisesRegex(devices.Refused, "held by session-a"):
            self.reserve(owner="session-b", revision=entry["revision"])
        code, output, _error = self.cli("status")
        self.assertEqual(code, 0)
        self.assertIn("overdue, which releases nothing", output)
        with self.assertRaisesRegex(ValueError, "future"):
            self.reserve("iPad", release_by=past)

    def test_a_vanished_run_is_an_orphan_kept_for_attended_recovery(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        entry = self.reserve(device=PHONE)
        with self.assertRaisesRegex(ValueError, "hostProcessIdentifier"):
            self.record.update("iPhone", owner="session-a", revision=entry["revision"], activeRun=True)
        entry = self.record.update("iPhone", owner="session-a", revision=entry["revision"], state="testing",
                                   activeRun=True, hostProcessIdentifier=child.pid)
        self.assertEqual(devices.condition(entry), "active")
        with self.assertRaisesRegex(devices.Refused, "active run"):
            self.record.release("iPhone", owner="session-a", revision=entry["revision"], outcome="o", restoration="r")
        with self.assertRaisesRegex(devices.Refused, "still running"):
            self.record.recover("iPhone", by="session-b", revision=entry["revision"], verified="nothing yet")
        child.kill()
        child.wait()
        self.assertEqual(devices.condition(entry), "orphan")
        with self.assertRaisesRegex(devices.Refused, "orphan"):
            self.reserve(owner="session-b", revision=entry["revision"])
        code, output, _error = self.cli("status")
        self.assertIn("kept for attended recovery", output)
        released = self.record.recover("iPhone", by="session-b", revision=entry["revision"],
                                       verified="no owned processes on the device; VoiceOver as recorded")
        self.assertEqual((released["state"], released["lastOwnerChatID"]), ("released", "session-a"))
        self.assertEqual(released["recovery"]["condition"], "orphan")
        self.reserve(owner="session-b", revision=released["revision"])

    def test_unverified_restoration_keeps_the_device_until_its_owner_releases_it(self):
        entry = self.reserve()
        entry = self.record.update("iPhone", owner="session-a", revision=entry["revision"], state="restoration-unverified")
        self.assertEqual(devices.condition(entry), "uncertain")
        with self.assertRaisesRegex(devices.Refused, "uncertain"):
            self.reserve(owner="session-b", revision=entry["revision"])
        for change in [{"uncertain": False}, {"state": "released"}]:
            with self.assertRaises(ValueError):
                self.record.update("iPhone", owner="session-a", revision=entry["revision"], **change)
        with self.assertRaisesRegex(ValueError, "outcome"):
            self.record.release("iPhone", owner="session-a", revision=entry["revision"], outcome="", restoration="")
        released = self.record.release("iPhone", owner="session-a", revision=entry["revision"], outcome="Xcode exit 0",
                                       restoration="VoiceOver as recorded; no owned processes")
        self.assertEqual(devices.condition(released), "released")
        self.assertIsNone(released["ownerChatID"])
        self.assertEqual(released["lastOwnerChatID"], "session-a")

    def test_one_device_is_never_held_under_two_keys_or_named_loosely(self):
        self.reserve(device=PHONE)
        with self.assertRaisesRegex(devices.Refused, "same device"):
            self.reserve("Phone alias", owner="session-b", device=PHONE)
        for name in ["booted", PHONE.lower(), "Owner's iPhone"]:
            with self.assertRaisesRegex(ValueError, "UDID"):
                self.reserve("iPad", device=name)
        entry = self.record.entry("iPhone")
        self.record.release("iPhone", owner="session-a", revision=entry["revision"], outcome="o", restoration="r")
        self.reserve("Phone alias", owner="session-b", device=PHONE)

    def test_a_held_lock_refuses_after_its_timeout_without_writing(self):
        self.reserve()
        before = self.path.read_bytes()
        descriptor = os.open(self.record.lock, os.O_RDWR)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        waiting = devices.Record(self.path, timeout=0.1)
        with self.assertRaisesRegex(TimeoutError, "nothing was changed"):
            waiting.update("iPhone", owner="session-a", revision=1, run="blocked")
        self.assertEqual(self.path.read_bytes(), before)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        self.assertEqual(waiting.update("iPhone", owner="session-a", revision=1, run="after")["revision"], 2)

    def test_an_unreadable_or_foreign_record_is_never_replaced(self):
        for text in ["{not json", json.dumps({"devices": {}})]:
            with self.subTest(text):
                self.path.write_text(text)
                with self.assertRaises(devices.Refused):
                    self.reserve()
                self.assertEqual(self.path.read_text(), text)

    def test_import_keeps_every_entry_from_both_records_once(self):
        newer = self.legacy("pair", {"kind": "handoff", "updatedAt": "2026-10-21T06:50:00+00:00", "devices": {
            "iPhone": {"device": PHONE, "ownerChatID": None, "state": "released", "activeRun": False,
                       "leaseRevision": "2026-10-20T16:48:00+00:00", "releasedAt": "2026-10-20T17:00:00+00:00",
                       "run": "newer"},
            "iPad": {"ownerChatID": "session-c", "state": "released", "activeRun": False,
                     "leaseRevision": "2026-10-20T07:26:00+00:00", "releasedAt": "2026-10-20T08:00:00+00:00"},
            "Duo": {"device": DUO, "ownerChatID": "session-d", "state": "reserved", "activeRun": False,
                    "leaseRevision": "2026-10-21T06:37:00+00:00"}},
            "peerReport": {"chatID": "session-c", "completedBothRuns": True}, "preservation": "owner data"})
        older = self.legacy("shared", {"devices": {
            "iPhone": {"device": PHONE, "ownerChatID": "session-b", "state": "released", "activeRun": False,
                       "leaseRevision": "2026-10-20T07:00:00+00:00", "releasedAt": "2026-10-20T07:30:00+00:00",
                       "run": "older"},
            "iPad": {"session": "session-e", "state": "reserved", "activeRun": False,
                     "reservedAt": "2026-10-20T09:00:00+00:00"}}})
        originals = {path: path.read_bytes() for path in (newer, older)}
        # Negative control: the earlier rule, reserving in the record updated last, misses session-e's hold.
        self.assertNotIn("session-e", newer.read_text())
        self.assertEqual(self.cli("status")[1].count("not imported"), 2)
        report = self.record.import_legacy([newer, older], by="session-x")
        self.assertEqual(report, [f"{newer}: 3 added, 0 merged, 0 already present",
                                  f"{older}: 0 added, 2 merged, 0 already present"])
        value = self.record.load()
        entries = value["devices"]
        self.assertEqual(set(entries), {"iPhone", "iPad", "Duo"})
        self.assertEqual(entries["iPhone"]["run"], "newer")
        self.assertEqual([version["run"] for version in entries["iPhone"]["importedVersions"]], ["older"])
        self.assertEqual(entries["iPad"]["session"], "session-e")
        self.assertEqual(entries["iPad"]["importedVersions"][0]["ownerChatID"], "session-c")
        self.assertEqual([devices.condition(entries[key]) for key in ("iPhone", "iPad", "Duo")],
                         ["released", "held", "held"])
        self.assertNotIn("uncertain", entries["iPad"])
        self.assertEqual(value["imports"][0]["fields"]["peerReport"], {"chatID": "session-c", "completedBothRuns": True})
        self.assertEqual({path: path.read_bytes() for path in (newer, older)}, originals)
        self.assertNotIn("not imported", self.cli("status")[1])
        self.assertEqual(self.record.import_legacy([newer, older], by="session-x"),
                         [f"{newer}: already imported", f"{older}: already imported"])
        self.assertEqual(self.record.load()["revision"], value["revision"])
        with self.assertRaisesRegex(devices.Refused, "held by None"):
            self.reserve("iPad", owner="session-y", revision=entries["iPad"]["revision"])

    def test_import_marks_conflicting_holds_uncertain_and_keeps_both(self):
        self.record.import_legacy([self.legacy("first", {"devices": {
            "iPad": {"ownerChatID": "session-e", "state": "reserved", "reservedAt": "2026-10-20T09:00:00+00:00"},
            "Duo": {"device": DUO, "ownerChatID": "session-d", "state": "reserved"}}})], by="session-x")
        second = self.legacy("second", {"devices": {
            "iPad": {"ownerChatID": "session-f", "state": "testing", "reservedAt": "2026-10-20T10:00:00+00:00"},
            "Duo spare": {"device": DUO, "ownerChatID": "session-g", "state": "reserved"}}})
        self.record.import_legacy([second], by="session-x")
        entries = self.record.load()["devices"]
        self.assertEqual(entries["iPad"]["ownerChatID"], "session-f")
        self.assertEqual(entries["iPad"]["importedVersions"][0]["ownerChatID"], "session-e")
        self.assertEqual([devices.condition(entries[key]) for key in ("iPad", "Duo", "Duo spare")], ["uncertain"] * 3)
        self.assertIn("Duo spare", entries["Duo"]["uncertainReason"])
        with self.assertRaisesRegex(devices.Refused, "uncertain"):
            self.reserve("iPad", owner="session-y", revision=entries["iPad"]["revision"])
        released = self.record.recover("iPad", by="session-x", revision=entries["iPad"]["revision"],
                                       verified="both sessions confirmed their runs ended")
        self.assertEqual(released["recovery"]["uncertainReason"], entries["iPad"]["uncertainReason"])
        before = self.path.read_bytes()
        broken = self.legacy("broken", {"devices": ["not", "entries"]})
        with self.assertRaisesRegex(devices.Refused, "nothing was imported"):
            self.record.import_legacy([second, broken], by="session-x")
        self.assertEqual(self.path.read_bytes(), before)

    def test_status_lists_the_mac_foreground_entry_free_then_with_its_holder_and_approval(self):
        self.assertIn(f"{devices.FOREGROUND}: free", self.cli("status")[1])
        entry = self.foreground(approval=approval(words="Use the screen for the Mac UI tests until 6"))
        self.assertNotIn("device", entry)
        self.assertEqual(entry["approval"]["words"], "Use the screen for the Mac UI tests until 6")
        code, output, _error = self.cli("status")
        self.assertEqual(code, 0)
        self.assertIn(f"{devices.FOREGROUND}: held; owner session-a, state reserved", output)
        self.assertIn(f"approved by owner at {entry['approval']['at']} until {entry['approval']['until']}", output)

    def test_a_second_foreground_reservation_is_refused(self):
        entry = self.foreground()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(devices.Refused, "held by session-a"):
            self.foreground(owner="session-b", revision=entry["revision"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_the_approval_window_is_required_checked_and_never_changed(self):
        invalid = [({"approval": None}, "owner's approval"), ({"device": PHONE}, "names no device"),
                   ({"approval": {"by": "owner", "at": later(-1)}}, "by, at and until"),
                   ({"approval": approval(at=later(5))}, "when the owner approved"),
                   ({"approval": approval(until=later(-5))}, "until"),
                   ({"approval": approval(until=later(20)), "release_by": later(30)}, "after the owner's approval ends")]
        for options, message in invalid:
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                self.foreground(**options)
        self.assertFalse(self.path.exists())
        entry = self.foreground(approval=approval(until="released"), release_by=later(600))
        for change in [{"approval": approval(until=later(600))}, {"ownedProcesses": []}]:
            with self.subTest(change=sorted(change)), self.assertRaisesRegex(ValueError, "itself"):
                self.record.update(devices.FOREGROUND, owner="session-a", revision=entry["revision"], **change)
        code, _output, error = self.cli("update", devices.FOREGROUND, "--owner", "session-a", "--revision",
                                        str(entry["revision"]), "--set", f"approval={json.dumps(approval())}")
        self.assertEqual(code, 2)
        self.assertIn("itself", error)

    def test_a_passed_approval_or_deadline_releases_nothing_and_refuses_foreground_work(self):
        entry = self.foreground()
        self.assertEqual(devices.require_foreground("session-a")["ownerChatID"], "session-a")
        with patch.object(devices, "datetime", Later):
            self.assertEqual(devices.condition(self.record.entry(devices.FOREGROUND)), "held")
            with self.assertRaisesRegex(devices.Refused, "approval .* ended"):
                devices.require_foreground("session-a")
            with self.assertRaisesRegex(devices.Refused, "held by session-a"):
                self.foreground(owner="session-b", revision=entry["revision"], release_by=later(300),
                                approval=approval(until=later(600)))
            output = self.cli("status")[1]
        self.assertIn("overdue, which releases nothing", output)
        self.assertIn("approval ended; foreground actions are refused", output)

    def test_the_foreground_check_refuses_other_sessions_and_orphans_and_passes_on_a_hosted_runner(self):
        with self.assertRaisesRegex(devices.Refused, "nobody holds"):
            devices.require_foreground("session-a")
        entry = self.foreground()
        for owner, message in [("session-b", "held by session-a"), (None, "name the session")]:
            with self.subTest(owner=owner), self.assertRaisesRegex(devices.Refused, message):
                devices.require_foreground(owner)
        self.assertEqual(self.cli("check", "--owner", "session-a")[0], 0)
        self.assertEqual(self.cli("check", "--owner", "session-b")[0], 2)
        with patch.dict(os.environ, {devices.OWNER: "session-a"}):
            self.assertEqual(self.cli("check")[0], 0)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.record.update(devices.FOREGROUND, owner="session-a", revision=entry["revision"], state="testing",
                           activeRun=True, hostProcessIdentifier=child.pid)
        self.assertEqual(devices.require_foreground("session-a")["state"], "testing")
        child.kill()
        child.wait()
        with self.assertRaisesRegex(devices.Refused, "orphan"):
            devices.require_foreground("session-a")
        # A hosted runner is not the owner's Mac.
        with patch.dict(os.environ, {"RUNNER_ENVIRONMENT": "github-hosted"}):
            self.assertIsNone(devices.require_foreground("session-b"))

    def test_release_waits_for_owned_processes_and_records_the_frontmost_restoration(self):
        entry = self.foreground()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        with self.assertRaisesRegex(devices.Refused, "not running"):
            self.record.update(devices.FOREGROUND, owner="session-a", revision=entry["revision"], own=[99999999])
        code, output, _error = self.cli("update", devices.FOREGROUND, "--owner", "session-a",
                                        "--revision", str(entry["revision"]), "--own", str(child.pid))
        self.assertEqual(code, 0)
        entry = json.loads(output)["entry"]
        self.assertEqual([item["pid"] for item in entry["ownedProcesses"]], [child.pid])
        with self.assertRaisesRegex(devices.Refused, "still running"):
            self.record.release(devices.FOREGROUND, owner="session-a", revision=entry["revision"], outcome="o",
                                restoration="r", frontmost="restored")
        with self.assertRaisesRegex(devices.Refused, "still running"):
            self.record.recover(devices.FOREGROUND, by="session-b", revision=entry["revision"], verified="v")
        child.kill()
        child.wait()
        with self.assertRaisesRegex(ValueError, "frontmost"):
            self.record.release(devices.FOREGROUND, owner="session-a", revision=entry["revision"], outcome="o",
                                restoration="r")
        code, output, _error = self.cli("release", devices.FOREGROUND, "--owner", "session-a", "--revision",
                                        str(entry["revision"]), "--outcome", "UI tests passed", "--restoration",
                                        "Keyboard Navigation and VoiceOver as recorded", "--frontmost", "not-ours")
        self.assertEqual(code, 0)
        released = json.loads(output)["entry"]
        self.assertEqual((released["state"], released["frontmost"]), ("released", "not-ours"))

    def test_a_foreground_lane_runs_only_for_the_session_holding_mac_foreground(self):
        project = self.root / "project"
        project.mkdir()
        (project / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Project", "lanes": {
            "ui": {"command": [sys.executable, "-c", "open('ran', 'a').write('ran')"], "foreground": True}}}))
        def run(owner):
            with patch.dict(os.environ, {devices.OWNER: owner} if owner else {}), \
                 patch.object(cli, "source_identity", return_value={}), contextlib.redirect_stderr(StringIO()) as error:
                return cli.main(["--project", str(project), "run", "ui"]), error.getvalue()
        self.assertEqual(run("session-a"), (2, f"eng: nobody holds {devices.FOREGROUND}; reserve it with the owner's "
                                               "approval before foreground work\n"))
        self.foreground()
        for owner in ["session-b", None]:
            with self.subTest(owner=owner):
                self.assertEqual(run(owner)[0], 2)
        self.assertFalse((project / "ran").exists())
        self.assertEqual(run("session-a")[0], 0)
        self.assertEqual((project / "ran").read_text(), "ran")

    def test_command_line_reports_revisions_and_refusals(self):
        code, output, _error = self.cli("reserve", "iPhone", "--owner", "session-a", "--revision", "0",
            "--purpose", "smoke", "--release-by", later(), "--device", PHONE,
            "--set", 'originalSettings={"voiceoverEnabled": false}', "--set", "preservation=owner apps and data")
        self.assertEqual(code, 0)
        shown = json.loads(output)
        self.assertEqual((shown["revision"], shown["condition"]), (1, "held"))
        self.assertEqual(shown["entry"]["originalSettings"], {"voiceoverEnabled": False})
        self.assertEqual(shown["entry"]["preservation"], "owner apps and data")
        code, _output, error = self.cli("release", "iPhone", "--owner", "session-b", "--revision", "1",
                                        "--outcome", "o", "--restoration", "r")
        self.assertEqual(code, 2)
        self.assertIn("nothing was changed", error)
        code, output, _error = self.cli("release", "iPhone", "--owner", "session-a", "--revision", "1",
                                        "--outcome", "Xcode exit 0", "--restoration", "verified")
        self.assertEqual(json.loads(output)["condition"], "released")
        self.assertIn("iPhone: released; last owner session-a", self.cli("status")[1])
        self.assertEqual(json.loads(self.cli("show", "iPad")[1])["revision"], 0)
        self.assertEqual(self.cli("path")[1].strip(), str(self.path))


if __name__ == "__main__":
    unittest.main()
