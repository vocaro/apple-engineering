"""Source identities, positive test counts, and path-safe evidence receipts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tests(text, minimum=1):
    counts = [int(n) for n in re.findall(r"Executed (\d+) tests?\b", text)]
    counts += [int(n) for n in re.findall(r"Test run with (\d+) tests?(?: in \d+ suites?)? (?:passed|failed)", text)]
    counts += [int(n) for n in re.findall(r"^Ran (\d+) tests?\b", text, flags=re.M)]
    if not counts or max(counts) < minimum:
        raise ValueError(f"Expected at least {minimum} executed tests; observed {max(counts, default=0)}")
    return max(counts)


def contained(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe evidence path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Evidence path escapes its root: {relative}")
    return path


def receipt(root, paths):
    return {"schemaVersion": 1, "files": {str(p): sha256(contained(root, p)) for p in paths}}


def verify(root):
    root = Path(root)
    value = json.loads((root / "receipt.json").read_text())
    if value.get("schemaVersion") != 1 or not isinstance(value.get("files"), dict) or not value["files"]:
        raise ValueError("Expected a nonempty version 1 evidence receipt")
    for name, expected in value["files"].items():
        if sha256(contained(root, name)) != expected:
            raise ValueError(f"Evidence changed: {name}")
    return len(value["files"])


def export_xcresults(bundles, destination):
    """Export serially; xcresulttool can contend across simultaneous exports."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for index, bundle in enumerate(bundles):
        target = destination / f"{index:03d}-{Path(bundle).stem}"
        subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(bundle),
                        "--output-path", str(target)], check=True, timeout=300)
