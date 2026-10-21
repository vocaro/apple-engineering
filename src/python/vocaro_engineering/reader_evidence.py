#!/usr/bin/env python3
"""Local result extraction, selective retention, receipts and evidence hashes.

Adapted from the issue 51 temporary retention/export helpers and receipt audits.
No command launches an app, controls a device or changes accessibility settings.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PROFILES = globals().get("PROFILES", {})
# Also the project's, from its adapter or as arguments: the profiles whose evidence must come
# from a simulator, the prefix of the app's own log lines, and the log lines withheld because
# they name a private location.
SIMULATOR_PROFILES = globals().get("SIMULATOR_PROFILES")
LOG_MARKER = globals().get("LOG_MARKER")
PRIVATE_LOG_LINES = globals().get("PRIVATE_LOG_LINES")
if PROFILES and SIMULATOR_PROFILES is None and LOG_MARKER is None and PRIVATE_LOG_LINES is None:
    # Pagepour's adapter, which defined only PROFILES before these existed. Remove this once it
    # defines them.
    SIMULATOR_PROFILES, LOG_MARKER, PRIVATE_LOG_LINES = (
        ("share-simulator", "mobile-windows"), "READER", ("READER CAPTURE ROOT ",))
IDENTITY_KEYS = {"deviceId", "deviceID", "deviceName", "deviceIdentifier", "udid"}


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def fresh(path):
    if path.exists() or path.is_symlink():
        raise ValueError("output already exists: {}".format(path))


def child(root, relative):
    """Reject absolute, escaping and symlink-escaping manifest paths."""
    root = root.resolve()
    path = Path(relative)
    if path.is_absolute():
        raise ValueError("manifest path must be relative")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("manifest path escapes its root")
    return target


def scrub(value):
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if key not in IDENTITY_KEYS}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"0x[0-9a-fA-F]+", "<address>", value)
    return value


def reader_log(value, marker=None, withheld=None):
    """The app's own log lines, which start with marker, the lines continuing them, and test cases."""
    marker = marker or LOG_MARKER
    withheld = tuple((PRIVATE_LOG_LINES or ()) if withheld is None else withheld)
    if not marker:
        raise ValueError("the project adapter must define LOG_MARKER, the prefix of the app's log lines")
    lines = []
    continuation = False
    for line in value.splitlines():
        if line.startswith(withheld):
            continuation = False
            continue  # A private location, such as a path holding a simulator's identity.
        if line.startswith(marker) or line.startswith("Test Case "):
            lines.append(scrub(line))
            continuation = line.startswith(marker)
        elif continuation and line and not re.match(r"^\s*t =|^\d{4}-|^/|^Test |^\*\*", line):
            lines.append(scrub(line))
        else:
            continuation = False
    return "\n".join(lines) + "\n"


def export_result(result, prefix):
    """Extract sequentially; incomplete outputs remain private after a failure."""
    outputs = [Path(str(prefix) + suffix) for suffix in
               ("-summary.json", "-tests.json", "-attachments")]
    for path in outputs:
        fresh(path)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for mode, path in zip(("summary", "tests"), outputs[:2]):
        data = subprocess.check_output([
            "xcrun", "xcresulttool", "get", "test-results", mode,
            "--path", str(result), "--format", "json",
        ])
        # Check JSON before saving an output that a later step might mistake for a receipt.
        json.loads(data)
        path.write_bytes(data)
    subprocess.run([
        "xcrun", "xcresulttool", "export", "attachments", "--path", str(result),
        "--output-path", str(outputs[2]),
    ], check=True, stdout=subprocess.DEVNULL)


def retain(prefix, destination, profile, text_only=False, simulator_profiles=None, marker=None, withheld=None):
    fresh(destination)
    source = Path(str(prefix) + "-attachments")
    rows = load(source / "manifest.json")
    metadata = {name: scrub(load(Path(str(prefix) + "-" + name + ".json")))
                for name in ("summary", "tests", "revision")}
    simulator_profiles = SIMULATOR_PROFILES if simulator_profiles is None else simulator_profiles
    if profile in (simulator_profiles or ()) and "simulator" not in str(metadata["revision"].get("host", "")).lower():
        raise ValueError(profile + " requires an explicit simulator host receipt")
    log = reader_log(Path(str(prefix) + ".log").read_text(encoding="utf-8"), marker, withheld)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage a complete package before exposing it at the requested destination.
    with tempfile.TemporaryDirectory(prefix=".reader-evidence-", dir=destination.parent) as stage:
        stage = Path(stage).resolve()
        manifest = []
        seen = set()
        for row in rows:
            case = row["testIdentifier"].split("/")[-1].replace("()", "")
            if not case or case in (".", "..") or case in seen:
                raise ValueError("invalid or colliding test case directory")
            seen.add(case)
            casepath = child(stage, case)
            casepath.mkdir()
            attachments = []
            for item in row["attachments"]:
                name = item["suggestedHumanReadableName"]
                if not name.startswith(PROFILES[profile]):
                    continue
                original = child(source, item["exportedFileName"])
                if original.suffix not in (".png", ".txt"):
                    raise ValueError("selected attachment must be PNG or UTF-8 text")
                if text_only and original.suffix != ".txt":
                    continue
                target = casepath / original.name
                fresh(target)
                content = original.read_bytes()
                if target.suffix == ".txt":
                    content = scrub(content.decode("utf-8")).encode("utf-8")
                target.write_bytes(content)
                entry = scrub(item)
                entry["retainedPath"] = str(target.relative_to(stage))
                entry["sha256"] = hashlib.sha256(content).hexdigest()
                attachments.append(entry)
            manifest.append({"testIdentifier": row["testIdentifier"], "attachments": attachments})
        write_json(stage / "manifest.json", manifest)
        for name, value in metadata.items():
            write_json(stage / (name + ".json"), value)
        (stage / "spoken-output.log").write_text(log, encoding="utf-8")
        stage.rename(destination)
    count = sum(len(row["attachments"]) for row in manifest)
    print("Retained {} custom attachments; review before publishing".format(count))


def receipt(output, files, metadata=None):
    fresh(output)
    value = load(metadata) if metadata else {}
    if not isinstance(value, dict) or "sha256" in value or "capturedAtUTC" in value:
        raise ValueError("metadata must be an object without sha256/capturedAtUTC")
    value["capturedAtUTC"] = datetime.now(timezone.utc).isoformat()
    value["sha256"] = {str(path.resolve()): digest(path) for path in files}
    write_json(output, value)


def verify_receipt(path):
    hashes = load(path)["sha256"]
    if not hashes:
        raise ValueError("empty receipt")
    for name, expected in hashes.items():
        actual = Path(name)
        if not actual.is_absolute():
            actual = path.parent / actual
        if digest(actual) != expected:
            raise ValueError("receipt hash mismatch: {}".format(name))
    print("Verified {} receipt files".format(len(hashes)))


def inventory(root, index):
    value = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.resolve() != index.resolve():
            name = str(path.relative_to(root))
            value[name] = digest(child(root, name))
    return value


def index_evidence(root, index):
    value = inventory(root, index)
    write_json(index, value)
    print("Indexed {} evidence files".format(len(value)))


def verify_evidence(root, index):
    expected = load(index)
    actual = inventory(root, index)
    # Validate index paths before comparing even if the local inventory is different.
    for name in expected:
        child(root, name)
    changed = [name for name in expected if actual.get(name) != expected[name]]
    extra = sorted(set(actual) - set(expected))
    if changed or extra:
        raise ValueError("evidence differs: {} missing/changed, {} unindexed".format(len(changed), len(extra)))
    print("Verified {} indexed evidence files".format(len(expected)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("export", help="sequentially extract a completed local xcresult")
    p.add_argument("result", type=Path)
    p.add_argument("prefix", type=Path)
    p = commands.add_parser("retain", help="retain and redact allowlisted synthetic reader evidence")
    p.add_argument("prefix", type=Path)
    p.add_argument("destination", type=Path)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--profile", choices=PROFILES, default="spoken")
    group.add_argument("--rotor", dest="profile", action="store_const", const="rotor")
    p.add_argument("--text-only", action="store_true", help="exclude screenshots when only text observations are qualified")
    p = commands.add_parser("receipt", help="capture current file hashes with supplied run metadata")
    p.add_argument("output", type=Path)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--metadata", type=Path)
    p = commands.add_parser("verify-receipt", help="check recorded files still match their receipt")
    p.add_argument("path", type=Path)
    for name in ("index", "verify"):
        p = commands.add_parser(name, help="{} a flat SHA256 evidence index".format(name))
        p.add_argument("root", type=Path)
        p.add_argument("--index", type=Path, help="default: ROOT/evidence-hashes.json")
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_result(args.result, args.prefix)
        elif args.command == "retain":
            retain(args.prefix, args.destination, args.profile, args.text_only)
        elif args.command == "receipt":
            receipt(args.output, args.files, args.metadata)
        elif args.command == "verify-receipt":
            verify_receipt(args.path)
        else:
            index = args.index or args.root / "evidence-hashes.json"
            if args.command == "index":
                index_evidence(args.root, index)
            else:
                verify_evidence(args.root, index)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, "error: {}\n".format(error))


if __name__ == "__main__":
    main()
