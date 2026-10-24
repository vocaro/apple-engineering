"""Small, strict project configuration without third-party dependencies."""
import json
import os
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parents[3]
# integrations/shared.py, copied into each project, keeps its own copy of these paths.
DEFAULT_TOOLKIT = "../vocaro-engineering"
FORMER_TOOLKIT = "../apple-engineering"
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
    if not isinstance(toolkit, dict) or set(toolkit) - {"path"} or not isinstance(toolkit.get("path", DEFAULT_TOOLKIT), str):
        raise ValueError("toolkit must contain only an optional checkout path")
    if value.get("integration", "direct-main") not in {"direct-main", "pull-request"}:
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
    lanes = value.get("lanes", {})
    for name, lane in lanes.items():
        if isinstance(lane, dict) and "parallel" in lane:
            group(name, lane, lanes)
            continue
        if not isinstance(lane, dict) or set(lane) - {"command", "resource", "minimumTests", "timeout", "foreground",
                                                       "buildHost"}:
            raise ValueError(f"Invalid lane {name}")
        for key in ["foreground", "buildHost"]:
            if key in lane and type(lane[key]) is not bool:
                raise ValueError(f"{name}.{key} must be true or false")
        if lane.get("buildHost") and (lane.get("foreground") or lane.get("resource", "light") == "light"):
            raise ValueError(f"{name}.buildHost needs a heavy or exclusive lane that does not take the screen")
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


RESOURCES = ["light", "heavy", "exclusive"]


def group(name, lane, lanes):
    """A lane group names other lanes to run side by side under its one admission, so it needs
    the heaviest resource among them (guides/parallel-tests.md)."""
    if set(lane) - {"parallel", "jobs", "resource", "buildHost"}:
        raise ValueError(f"Lane group {name} takes only parallel, jobs, resource and buildHost")
    members = lane["parallel"]
    if not isinstance(members, list) or not members or len(set(members)) != len(members) \
            or any(not isinstance(member, str) for member in members):
        raise ValueError(f"{name}.parallel must list distinct lane names")
    resource = lane.get("resource", "light")
    if resource not in RESOURCES:
        raise ValueError(f"Invalid resource for {name}")
    for member in members:
        other = lanes.get(member)
        if not isinstance(other, dict) or "command" not in other:
            raise ValueError(f"{name}.parallel names {member}, which is not a lane with a command")
        if other.get("foreground"):
            raise ValueError(f"{name}.parallel names {member}, which takes the screen and runs alone")
        if RESOURCES.index(other.get("resource", "light")) > RESOURCES.index(resource):
            raise ValueError(f"{name} runs {member} under its own admission, so it needs a resource of at least "
                             f"{other.get('resource')}")
    if "jobs" in lane and (type(lane["jobs"]) is not int or not 1 <= lane["jobs"] <= len(members)):
        raise ValueError(f"{name}.jobs must be from 1 to the number of its lanes")
    if "buildHost" in lane and type(lane["buildHost"]) is not bool:
        raise ValueError(f"{name}.buildHost must be true or false")
    if lane.get("buildHost") and resource == "light":
        raise ValueError(f"{name}.buildHost needs a heavy or exclusive lane that does not take the screen")


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
