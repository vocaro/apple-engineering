"""Shared engineering entry point. Initialization never starts a build or hosted job."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import __version__, docs, evidence, processes, resources
from .config import TOOLKIT_ROOT, CAPABILITIES, load, source_identity


def initialize(root, args):
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "engineering.json"
    if config_path.exists(): load(root)
    if not config_path.exists():
        config_path.write_text(json.dumps({"schemaVersion": 1, "name": args.name or root.name,
            "toolkit": {"path": os.path.relpath(TOOLKIT_ROOT, root)},
            "capabilities": args.capability, "lanes": {}, "exceptions": []}, indent=2) + "\n")
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    launcher = scripts / "eng"
    if not launcher.exists():
        shutil.copyfile(TOOLKIT_ROOT / "integrations/eng.py", launcher)
        launcher.chmod(0o755)
    agents = root / "AGENTS.md"
    if not agents.exists():
        agents.write_text("# Contributor instructions\n\nRead shared guidance before work: `python3 scripts/eng instructions`.\n\nRecord project-specific product rules and justified exceptions here.\n")
    bridge = root / "CLAUDE.md"
    if not bridge.exists(): bridge.write_text("Read [AGENTS.md](AGENTS.md) before work.\n")
    load(root)
    print(f"Initialized {root}; existing instructions and commands were preserved")


def instructions(config):
    print((TOOLKIT_ROOT / "agents/core.md").read_text())
    for capability in config.get("capabilities", []):
        print((TOOLKIT_ROOT / "agents/capabilities" / f"{capability}.md").read_text())
    for exception in config.get("exceptions", []):
        print(f"Project exception — {exception['rule']}: {exception['reason']}")


def refresh_policy(root):
    subprocess.run(["git", "-C", str(TOOLKIT_ROOT), "fetch", "origin",
                    "refs/heads/main:refs/remotes/origin/main"], check=True, timeout=120)
    commit = subprocess.check_output(["git", "-C", str(TOOLKIT_ROOT), "rev-parse", "origin/main"], text=True).strip()
    text = subprocess.check_output(["git", "-C", str(TOOLKIT_ROOT), "show", f"{commit}:policies/shared-host.md"], text=True)
    print(f"Policy source: {commit}\n\n{text}")
    return commit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("--name")
    init.add_argument("--capability", action="append", choices=sorted(CAPABILITIES), default=[])
    commands.add_parser("doctor")
    commands.add_parser("instructions")
    policy = commands.add_parser("policy")
    policy.add_argument("operation", choices=["refresh"])
    run = commands.add_parser("run")
    run.add_argument("lane")
    evid = commands.add_parser("evidence")
    evid.add_argument("operation", choices=["verify"])
    evid.add_argument("directory", type=Path)
    documentation = commands.add_parser("docs")
    documentation.add_argument("operation", choices=["check"])
    documentation.add_argument("paths", nargs="*")
    knowledge = commands.add_parser("knowledge")
    knowledge.add_argument("query", nargs="?", default="")
    source = commands.add_parser("source")
    source.add_argument("name", choices=["voiceover-ax-observer.swift", "voiceover-link-verbosity.swift",
                                        "probe-simulator-voiceover-activation.m"])
    args = parser.parse_args(argv)
    root = args.project.resolve()
    try:
        if args.action == "init":
            initialize(root, args)
            return 0
        config = load(root)
        if args.action == "instructions": instructions(config)
        elif args.action == "doctor":
            required = {"git", "python3"}
            if any(c.startswith("simulator") or c == "packaging" for c in config.get("capabilities", [])):
                required |= {"xcrun", "xcodebuild"}
            missing = sorted(name for name in required if not shutil.which(name))
            print(json.dumps({"project": config["name"], "toolkit": str(TOOLKIT_ROOT),
                "source": source_identity(TOOLKIT_ROOT), "capabilities": config.get("capabilities", []),
                "missingCommands": missing}, indent=2))
            return int(bool(missing))
        elif args.action == "policy": refresh_policy(root)
        elif args.action == "source":
            from .support import source_path
            print(source_path(args.name))
        elif args.action == "docs":
            failures = docs.check(root, args.paths or None)
            print("\n".join(failures) if failures else "Documentation checks passed")
            return int(bool(failures))
        elif args.action == "evidence": print(f"Verified {evidence.verify(args.directory)} evidence files")
        elif args.action == "knowledge":
            entries = json.loads((TOOLKIT_ROOT / "knowledge/index.json").read_text())["entries"]
            for item in entries:
                if args.query.lower() in (item["title"] + " " + item["path"]).lower():
                    print(f"{item['id']}: {item['title']} — {TOOLKIT_ROOT / item['path']}")
        elif args.action == "run":
            lane = config.get("lanes", {}).get(args.lane)
            if lane is None: raise ValueError(f"No configured lane: {args.lane}")
            resource = lane.get("resource", "light")
            policy_commit = refresh_policy(root) if resource != "light" else None
            directory = root / ".build/engineering" / args.lane
            directory.mkdir(parents=True, exist_ok=True)
            receipt = {"project": source_identity(root), "toolkit": source_identity(TOOLKIT_ROOT),
                       "policy": policy_commit, "command": lane["command"]}
            def execute():
                try:
                    result = processes.run(lane["command"], cwd=root, log_path=directory / "run.log",
                                           timeout=lane.get("timeout"))
                    receipt["exitStatus"] = result
                except BaseException as error:
                    receipt["outcome"] = "failed-or-interrupted"
                    receipt["error"] = str(error)
                    raise
                finally:
                    (directory / "source.json").write_text(json.dumps(receipt, indent=2) + "\n")
                return result
            if resource == "light": result = execute()
            else:
                with resources.Admission(args.lane, exclusive=resource == "exclusive"):
                    result = execute()
            # The command has a confirmed terminal result. Coverage validation cannot turn
            # that completed process into an orphan reservation.
            if result == 0 and lane.get("minimumTests"):
                evidence.require_tests((directory / "run.log").read_text(), lane["minimumTests"])
            return result
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"eng: {error}", file=sys.stderr)
        return 2
