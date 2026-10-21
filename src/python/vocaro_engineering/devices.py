"""One device handoff record for the shared host, changed only under its lock.

Physical devices and reserved-pool simulators are used only under a reservation recorded here.
Sessions used to keep ad hoc JSON files in /private/tmp. Two live copies let two sessions reserve
one device in different files, unlocked read-modify-write could lose entries, and the restart
after the 2026-10-14 panic emptied /private/tmp while device work could still be running.

The record lives in the account's Application Support directory, found independently of HOME
and TMPDIR so that every session finds the same one. A change takes an exclusive lock, reads the
record fresh, refuses unless the entry is still at the revision the caller read, and replaces the
file whole. The lock covers one change, never a reservation, and the kernel drops it with its
process. Like a heavy-work guard, an entry is never released by a deadline or a vanished process:
an active run whose recorded process is gone is an orphan, kept for attended recovery.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import glob
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import sys
import tempfile
import time

from .resources import process_start

SCHEMA = 1
OVERRIDE = "VOCARO_DEVICE_RECORD"
ABOUT = ("Device reservations on this Mac. Change entries only through "
         "`python3 -m vocaro_engineering.devices` (apple-engineering guides/shared-host.md).")
# Earlier ad hoc records. Status names one whose current bytes were never imported.
LEGACY = "/private/tmp/*device-handoff*.json"
UDID = re.compile(r"[0-9A-F]{8}(?:-[0-9A-F]{4,16}){1,4}|[0-9A-F]{40}")
# Written only by the record's own operations, which say who changed ownership and why.
MANAGED = {"revision", "ownerChatID", "lastOwnerChatID", "previousLease", "recovery", "importedFrom",
           "importedVersions", "uncertainReason", "hostProcessStart"}
TIMES = ("leaseRevision", "releasedAt", "reservedAt", "leasedAt", "updatedAt")
EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class Refused(RuntimeError):
    """The record refused a change; nothing was written."""


class Stale(Refused):
    """The entry changed after the caller read it."""


def default_path():
    """The account's record. A HOME or TMPDIR private to one session must not start another."""
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if sys.platform == "darwin":
        return home / "Library/Application Support/vocaro-engineering/device-handoff.json"
    return home / ".local/state/vocaro-engineering/device-handoff.json"


def record_path():
    """VOCARO_DEVICE_RECORD names an isolated record for tests; sessions use the default."""
    return Path(os.environ[OVERRIDE]) if os.environ.get(OVERRIDE) else default_path()


def restart_emptied(path):
    path = Path(os.path.abspath(path))
    for candidate in (path, path.resolve()):
        for root in (Path("/tmp"), Path("/private/tmp")):
            if candidate == root or root in candidate.parents:
                return True
    return False


def now():
    return datetime.now(timezone.utc).isoformat()


def moment(value):
    """A time-zone-aware time from ISO 8601 text, or None."""
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else None


def condition(entry):
    """released, held, active, orphan or uncertain. Reading a condition never changes an entry."""
    if entry.get("uncertain") or entry.get("state") == "restoration-unverified":
        return "uncertain"
    if entry.get("activeRun"):
        pid, start = entry.get("hostProcessIdentifier"), entry.get("hostProcessStart")
        alive = isinstance(pid, int) and pid > 0 and start is not None and process_start(pid) == start
        return "active" if alive else "orphan"
    return "released" if entry.get("state") == "released" else "held"


def _owned(key, entry, owner):
    if entry is None:
        raise Refused(f"{key} has no entry; nothing was changed")
    if entry.get("ownerChatID") != owner or entry.get("state") == "released":
        raise Refused(f"{key} is not held by {owner} (owner {entry.get('ownerChatID')}, state "
                      f"{entry.get('state')}); nothing was changed")


def _latest(entry):
    times = [moment(entry.get(name)) for name in TIMES]
    return max([value for value in times if value is not None] or [EPOCH])


def _content(entry):
    return {key: value for key, value in entry.items()
            if key not in ("revision", "importedFrom", "importedVersions", "uncertain", "uncertainReason")}


def _merge(current, incoming):
    """One entry from the record's version and an imported one, discarding neither; None if known.

    A held version stays current over a released one, so a live reservation is preserved; among
    equals the later activity wins. Two held versions leave the entry uncertain for recovery.
    """
    if current is None:
        return {"revision": 1, **incoming}
    earlier = current.get("importedVersions", [])
    if any(_content(incoming) == _content(version) for version in [current, *earlier]):
        return None
    present = {key: value for key, value in current.items() if key != "importedVersions"}
    held = [version for version in (present, incoming) if condition(version) != "released"]
    winner = max(held or [present, incoming], key=_latest)
    loser = incoming if winner is present else present
    merged = {"revision": current.get("revision", 0) + 1,
              **{key: value for key, value in winner.items() if key != "revision"}}
    merged["importedVersions"] = [*earlier, loser]
    if len(held) > 1 or current.get("uncertain"):
        merged["uncertain"] = True
        merged["uncertainReason"] = current.get("uncertainReason") or (
            "imported records hold this device for different runs; resolve ownership before use")
    return merged


class Record:
    def __init__(self, path=None, timeout=30):
        self.path = Path(os.path.abspath(path or record_path()))
        if restart_emptied(self.path):
            raise ValueError(f"{self.path} is emptied by a restart; the device record is {default_path()}")
        self.lock = self.path.with_name(self.path.name + ".lock")
        self.timeout = timeout

    def load(self):
        """The record as last replaced. Reading needs no lock: every change replaces the file whole."""
        try:
            value = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"vocaroDeviceHandoff": SCHEMA, "about": ABOUT, "revision": 0, "devices": {}, "imports": []}
        except ValueError as error:
            raise Refused(f"{self.path} cannot be read ({error}); nothing was changed") from error
        if not isinstance(value, dict) or value.get("vocaroDeviceHandoff") != SCHEMA or not isinstance(value.get("devices"), dict):
            raise Refused(f"{self.path} is not a version {SCHEMA} device record; nothing was changed")
        return value

    def entry(self, key):
        return self.load()["devices"].get(key)

    @contextlib.contextmanager
    def _exclusive(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            started = time.monotonic()
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - started >= self.timeout:
                        raise TimeoutError(f"{self.lock} stayed locked for {self.timeout}s; nothing was changed") from None
                    time.sleep(0.02)
            yield
        finally:
            os.close(descriptor)

    def _replace(self, record):
        record["revision"] = record.get("revision", 0) + 1
        record["updatedAt"] = now()
        staged = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=self.path.parent, prefix=".device-handoff-", delete=False) as stream:
                staged = Path(stream.name)
                json.dump(record, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, self.path)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _change(self, key, revision, change):
        """Compare-and-replace one entry: refuse unless it is still at the revision the caller read."""
        with self._exclusive():
            record = self.load()
            current = record["devices"].get(key)
            found = current.get("revision", 0) if current is not None else 0
            if found != revision:
                raise Stale(f"{key} is at revision {found}, not {revision}; read it again. Nothing was changed")
            entry = change(current, record)
            entry.pop("revision", None)
            record["devices"][key] = {"revision": found + 1, **entry}
            self._replace(record)
            return record["devices"][key]

    def reserve(self, key, *, owner, revision, purpose, release_by, device=None, title=None, details=None):
        """Claim a released or new entry. The previous lease is kept, one generation deep."""
        details = dict(details or {})
        if not owner or not purpose:
            raise ValueError("a reservation names its owner and purpose")
        if MANAGED & details.keys():
            raise ValueError(f"the record writes {', '.join(sorted(MANAGED & details.keys()))} itself")
        deadline = moment(release_by)
        if deadline is None or deadline <= datetime.now(timezone.utc):
            raise ValueError("the expected release must be a future ISO 8601 time with a time zone")
        if device is not None and not UDID.fullmatch(device):
            raise ValueError("name the device by its canonical uppercase UDID, never a name or 'booted'")
        json.dumps(details)

        def change(current, record):
            if current is not None and condition(current) != "released":
                raise Refused(f"{key} is {condition(current)} by {current.get('ownerChatID')}; obtain its "
                              "release or attended recovery first. Nothing was changed")
            identifier = device or (current or {}).get("device")
            for other, entry in record["devices"].items():
                same = isinstance(entry.get("device"), str) and identifier and entry["device"].upper() == identifier.upper()
                if other != key and same and condition(entry) != "released":
                    raise Refused(f"the same device is {condition(entry)} as {other}; nothing was changed")
            entry = {**details, "device": identifier, "ownerChatID": owner, "ownerChatTitle": title,
                     "state": "reserved", "activeRun": False, "purpose": purpose, "reservedAt": now(),
                     "expectedReleaseBy": release_by}
            if current is not None:
                entry["previousLease"] = {name: value for name, value in current.items() if name != "previousLease"}
            return {name: value for name, value in entry.items() if value is not None}
        return self._change(key, revision, change)

    def update(self, key, *, owner, revision, **changes):
        """Change the caller's own held entry. An active run names the process whose end ends it."""
        if MANAGED & changes.keys():
            raise ValueError(f"the record writes {', '.join(sorted(MANAGED & changes.keys()))} itself")
        if changes.get("state") == "released":
            raise ValueError("release with release(), which records the outcome and restoration")
        if "uncertain" in changes and not changes["uncertain"]:
            raise ValueError("uncertainty ends only by release or recovery, which record the verification")
        if changes.get("activeRun") and "hostProcessIdentifier" not in changes:
            raise ValueError("an active run records hostProcessIdentifier, the process whose end ends it")
        if changes.get("hostProcessIdentifier") is not None:
            changes["hostProcessStart"] = process_start(changes["hostProcessIdentifier"])
            if changes["hostProcessStart"] is None:
                raise Refused("the run's process is not running; record its terminal result instead")
        json.dumps(changes)

        def change(current, _record):
            _owned(key, current, owner)
            return {**current, **changes}
        return self._change(key, revision, change)

    def release(self, key, *, owner, revision, outcome, restoration):
        """Release the caller's own entry with its terminal outcome and restoration checks."""
        if not outcome or not restoration:
            raise ValueError("a release records the terminal outcome and the restoration checks")

        def change(current, _record):
            _owned(key, current, owner)
            if current.get("activeRun"):
                raise Refused(f"{key} has an active run; record its confirmed terminal result first. "
                              "Nothing was changed")
            entry = {name: value for name, value in current.items() if name not in ("uncertain", "uncertainReason")}
            entry.update({"state": "released", "activeRun": False, "ownerChatID": None,
                          "lastOwnerChatID": owner, "releasedAt": now(), "run": outcome,
                          "restoration": restoration})
            return entry
        return self._change(key, revision, change)

    def recover(self, key, *, by, revision, verified):
        """Attended recovery of an entry whose owner cannot release it, once its work has stopped."""
        if not by or not verified:
            raise ValueError("recovery records who verified the device and what they verified")

        def change(current, _record):
            state = condition(current) if current is not None else "absent"
            if state in ("absent", "released"):
                raise Refused(f"{key} is {state}; there is nothing to recover")
            if state == "active":
                raise Refused(f"{key}'s run process {current.get('hostProcessIdentifier')} is still running; "
                              "recovery waits for it. Nothing was changed")
            entry = {name: value for name, value in current.items() if name not in ("uncertain", "uncertainReason")}
            entry.update({"state": "released", "activeRun": False, "ownerChatID": None,
                          "lastOwnerChatID": current.get("ownerChatID"), "releasedAt": now(),
                          "recovery": {"by": by, "at": now(), "verified": verified, "condition": state,
                                       "state": current.get("state"),
                                       "uncertainReason": current.get("uncertainReason")}})
            return entry
        return self._change(key, revision, change)

    def import_legacy(self, paths, *, by):
        """Merge earlier ad hoc records once each, preserving every entry; the files stay untouched."""
        if not by:
            raise ValueError("name the importing session")
        sources = []
        for path in map(Path, paths):
            data = path.read_bytes()
            try:
                value = json.loads(data)
            except ValueError as error:
                raise Refused(f"{path} cannot be read ({error}); nothing was imported") from error
            entries = value.get("devices") if isinstance(value, dict) else None
            if not isinstance(entries, dict) or not all(isinstance(entry, dict) for entry in entries.values()):
                raise Refused(f"{path} has no devices object of entries; nothing was imported")
            sources.append((path, data, value, path.stat().st_mtime))
        report = []
        with self._exclusive():
            record = self.load()
            imports = record.setdefault("imports", [])
            for path, data, value, modified in sources:
                digest = hashlib.sha256(data).hexdigest()
                if any(item.get("sha256") == digest for item in imports):
                    report.append(f"{path}: already imported")
                    continue
                counts = {"added": 0, "merged": 0, "already present": 0}
                for key, legacy in value["devices"].items():
                    incoming = dict(legacy)
                    if "revision" in incoming:
                        incoming["legacyRevision"] = incoming.pop("revision")
                    incoming["importedFrom"] = {"path": str(path), "sha256": digest}
                    current = record["devices"].get(key)
                    merged = _merge(current, incoming)
                    if merged is None:
                        counts["already present"] += 1
                        continue
                    counts["added" if current is None else "merged"] += 1
                    record["devices"][key] = merged
                imports.append({"path": str(path), "sha256": digest, "bytes": len(data),
                                "modifiedAt": datetime.fromtimestamp(modified, timezone.utc).isoformat(),
                                "importedAt": now(), "importedBy": by, "devices": list(value["devices"]),
                                "fields": {name: field for name, field in value.items() if name != "devices"}})
                report.append(f"{path}: " + ", ".join(f"{count} {name}" for name, count in counts.items()))
            # One device held under two keys, from different records, is unclear ownership.
            holders = {}
            for key, entry in record["devices"].items():
                if isinstance(entry.get("device"), str) and condition(entry) != "released":
                    holders.setdefault(entry["device"].upper(), []).append(key)
            for keys in holders.values():
                for key in keys if len(keys) > 1 else []:
                    entry = record["devices"][key]
                    if not entry.get("uncertain"):
                        entry.update(revision=entry.get("revision", 0) + 1, uncertain=True,
                                     uncertainReason=f"the same device is also held as {', '.join(k for k in keys if k != key)}")
            if len(report) > sum(line.endswith("already imported") for line in report):
                self._replace(record)
        return report


def _describe(key, entry):
    state = condition(entry)
    parts = [f"{key}: {state}"]
    if state == "released":
        parts.append(f"last owner {entry.get('lastOwnerChatID') or entry.get('ownerChatID') or 'unrecorded'}, "
                     f"released {entry.get('releasedAt') or 'at an unrecorded time'}")
    else:
        parts.append(f"owner {entry.get('ownerChatID')}, state {entry.get('state')}, "
                     f"expected release {entry.get('expectedReleaseBy')}")
        deadline = moment(entry.get("expectedReleaseBy"))
        if deadline is not None and deadline < datetime.now(timezone.utc):
            parts.append("overdue, which releases nothing")
        if state == "orphan":
            parts.append(f"run process {entry.get('hostProcessIdentifier')} is gone or unrecorded; kept for attended recovery")
        if state == "uncertain":
            parts.append((entry.get("uncertainReason") or "termination or restoration is unverified")
                         + "; kept for attended recovery")
    parts.append(f"revision {entry.get('revision', 0)}")
    return "; ".join(parts)


def status(record):
    value = record.load()
    source = f" (from {OVERRIDE})" if os.environ.get(OVERRIDE) else ""
    print(f"Device record {record.path}{source}: revision {value.get('revision', 0)}, updated {value.get('updatedAt', 'never')}")
    for key, entry in value["devices"].items():
        print(_describe(key, entry))
    imported = {item.get("sha256") for item in value.get("imports", [])}
    for legacy in sorted(glob.glob(LEGACY)):
        try:
            digest = hashlib.sha256(Path(legacy).read_bytes()).hexdigest()
        except OSError:
            continue
        if digest not in imported:
            print(f"Legacy record {legacy} has entries not imported: import it, then stop writing it")


def _fields(pairs):
    result = {}
    for pair in pairs or []:
        name, separator, text = pair.partition("=")
        if not separator or not name:
            raise ValueError(f"--set takes FIELD=VALUE, not {pair}")
        try:
            result[name] = json.loads(text)
        except ValueError:
            result[name] = text
    return result


def _report(key, entry):
    print(json.dumps({"key": key, "revision": (entry or {}).get("revision", 0),
                      "condition": condition(entry) if entry else None, "entry": entry}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m vocaro_engineering.devices",
                                     description="Read or change the shared device handoff record.")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("path", help="print the record's location")
    commands.add_parser("status", help="every entry's condition, and legacy records not yet imported")
    show = commands.add_parser("show", help="one entry with the revision a change must name")
    show.add_argument("key")
    reserve = commands.add_parser("reserve", help="claim a released or new entry")
    reserve.add_argument("key")
    reserve.add_argument("--owner", required=True)
    reserve.add_argument("--revision", type=int, required=True)
    reserve.add_argument("--purpose", required=True)
    reserve.add_argument("--release-by", required=True)
    reserve.add_argument("--device")
    reserve.add_argument("--title")
    reserve.add_argument("--set", action="append", metavar="FIELD=JSON")
    update = commands.add_parser("update", help="change your own held entry")
    update.add_argument("key")
    update.add_argument("--owner", required=True)
    update.add_argument("--revision", type=int, required=True)
    update.add_argument("--set", action="append", metavar="FIELD=JSON", required=True)
    release = commands.add_parser("release", help="release your own entry")
    release.add_argument("key")
    release.add_argument("--owner", required=True)
    release.add_argument("--revision", type=int, required=True)
    release.add_argument("--outcome", required=True)
    release.add_argument("--restoration", required=True)
    recover = commands.add_parser("recover", help="attended release of an entry its owner cannot release")
    recover.add_argument("key")
    recover.add_argument("--by", required=True)
    recover.add_argument("--revision", type=int, required=True)
    recover.add_argument("--verified", required=True)
    importer = commands.add_parser("import", help="merge earlier ad hoc records, preserving every entry")
    importer.add_argument("paths", nargs="+")
    importer.add_argument("--by", required=True)
    args = parser.parse_args(argv)
    try:
        record = Record()
        if args.action == "path":
            print(record.path)
        elif args.action == "status":
            status(record)
        elif args.action == "show":
            _report(args.key, record.entry(args.key))
        elif args.action == "reserve":
            _report(args.key, record.reserve(args.key, owner=args.owner, revision=args.revision,
                purpose=args.purpose, release_by=args.release_by, device=args.device, title=args.title,
                details=_fields(args.set)))
        elif args.action == "update":
            _report(args.key, record.update(args.key, owner=args.owner, revision=args.revision, **_fields(args.set)))
        elif args.action == "release":
            _report(args.key, record.release(args.key, owner=args.owner, revision=args.revision,
                                             outcome=args.outcome, restoration=args.restoration))
        elif args.action == "recover":
            _report(args.key, record.recover(args.key, by=args.by, revision=args.revision, verified=args.verified))
        elif args.action == "import":
            print("\n".join(record.import_legacy(args.paths, by=args.by)))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"devices: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
