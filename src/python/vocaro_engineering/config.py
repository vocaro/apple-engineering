"""Small, strict project configuration without third-party dependencies."""
import json
import os
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES = {
    "simulator-disposable", "simulator-pool", "voiceover", "background-mac",
    "packaging", "measurement", "native-python", "external-validation",
    "background-processing", "app-extensions", "data-protection", "file-handoff",
    "storekit", "foundation-models", "background-assets",
}


def load(root):
    root = Path(root).resolve()
    value = json.loads((root / "engineering.json").read_text())
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ValueError("engineering.json requires schemaVersion 1")
    allowed = {"schemaVersion", "name", "toolkit", "capabilities", "lanes", "exceptions",
               "integration", "hostedRepositories", "voiceover", "repository", "spelling"}
    if set(value) - allowed:
        raise ValueError(f"Unknown configuration keys: {sorted(set(value) - allowed)}")
    if not isinstance(value.get("name"), str) or not value["name"]:
        raise ValueError("Project name must be a nonempty string")
    toolkit = value.get("toolkit", {})
    if not isinstance(toolkit, dict) or set(toolkit) - {"path"} or not isinstance(toolkit.get("path", "../apple-engineering"), str):
        raise ValueError("toolkit must contain only an optional checkout path")
    if value.get("integration", "pull-request") not in {"direct-main", "pull-request"}:
        raise ValueError("Unknown integration policy")
    repositories = value.get("hostedRepositories", [])
    if not isinstance(repositories, list) or any(not isinstance(r, str) or r.count("/") != 1 for r in repositories):
        raise ValueError("hostedRepositories must be owner/repository names")
    voiceover = value.get("voiceover", {})
    if not isinstance(voiceover, dict) or set(voiceover) - {"workflows"}:
        raise ValueError("voiceover supports only an explicit workflow allowlist")
    workflows = voiceover.get("workflows", [])
    if not isinstance(workflows, list) or any(not isinstance(w, str) or not w for w in workflows):
        raise ValueError("VoiceOver workflows must be nonempty names")
    capabilities = value.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(c, str) for c in capabilities):
        raise ValueError("capabilities must be a list of names")
    if set(capabilities) - CAPABILITIES:
        raise ValueError(f"Unknown capabilities: {sorted(set(capabilities) - CAPABILITIES)}")
    if len(set(capabilities)) != len(capabilities):
        raise ValueError("Duplicate capability")
    if {"simulator-disposable", "simulator-pool"} <= set(capabilities):
        raise ValueError("Choose one simulator ownership policy")
    if not isinstance(value.get("lanes", {}), dict):
        raise ValueError("lanes must be an object")
    for name, lane in value.get("lanes", {}).items():
        if not isinstance(lane, dict) or set(lane) - {"command", "resource", "minimumTests", "timeout", "foreground"}:
            raise ValueError(f"Invalid lane {name}")
        if "foreground" in lane and type(lane["foreground"]) is not bool:
            raise ValueError(f"{name}.foreground must be true or false")
        command = lane.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise ValueError(f"Lane {name} needs an argv list, never shell source")
        if lane.get("resource", "light") not in {"light", "heavy", "exclusive"}:
            raise ValueError(f"Invalid resource for {name}")
        for key in ["minimumTests", "timeout"]:
            if key in lane and (type(lane[key]) is not int or lane[key] <= 0):
                raise ValueError(f"{name}.{key} must be a positive integer")
    spelling = value.get("spelling", {})
    if not isinstance(spelling, dict) or set(spelling) - {"skip", "exemptPhrases", "exemptRuns", "exemptTokens"}:
        raise ValueError("spelling supports only skip, exemptPhrases, exemptRuns and exemptTokens")
    for key, entries in spelling.items():
        if not isinstance(entries, dict) or any(not isinstance(k, str) or not k.strip() or not isinstance(r, str)
                                                or not r.strip() for k, r in entries.items()):
            raise ValueError(f"spelling.{key} maps each entry to the reason it is kept")
    exceptions = value.get("exceptions", [])
    if not isinstance(exceptions, list) or any(not isinstance(x, dict) or not all(isinstance(x.get(k), str) and x[k] for k in ["rule", "reason"]) for x in exceptions):
        raise ValueError("Exceptions require a rule and a reason")
    return value


def source_identity(root):
    import subprocess
    import hashlib
    root = Path(root).resolve()
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=30)
    revision = result.stdout.strip() if result.returncode == 0 else None
    diff = subprocess.run(["git", "-C", str(root), "diff", "--binary", "HEAD"], capture_output=True, timeout=30)
    untracked = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
                               capture_output=True, timeout=30)
    digest = hashlib.sha256(diff.stdout)
    for raw in sorted(untracked.stdout.split(b"\0")):
        if not raw: continue
        path = root / os.fsdecode(raw)
        digest.update(raw + b"\0")
        if path.is_symlink(): digest.update(os.readlink(path).encode())
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return {"revision": revision, "workingChangesSHA256": digest.hexdigest()}
