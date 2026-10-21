"""Portable Markdown link and agent-entry-size checks."""
from pathlib import Path
import re
import os
import subprocess
from urllib.parse import unquote, urlsplit


def check(root, paths=None):
    root = Path(root).resolve()
    failures = []
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, timeout=30)
    tracked_names = {os.fsdecode(p) for p in tracked.stdout.split(b"\0") if p}
    tracked_lower = {p.lower() for p in tracked_names}
    if paths is not None:
        files = paths
    else:
        # Current subject docs are maintained; historical measurement attachments may be
        # intentionally external/ignored and must not be rewritten by a general doc check.
        files = list(root.glob("*.md"))
        for folder in ["doc", "guides", "knowledge", "agents", "policies"]:
            files.extend(p for p in (root / folder).rglob("*.md")
                if not any(part.startswith(".") or part in {"licenses", "ThirdParty", "Vendor"}
                           for part in p.relative_to(root / folder).parts))
    for path in files:
        path = Path(path)
        if not path.is_absolute(): path = root / path
        if path.name == "AGENTS.md" and path.stat().st_size >= 32768:
            failures.append(f"{path}: agent instructions reach 32 KiB")
        text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
        for raw in re.findall(r"\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text):
            target = unquote(raw.strip("<>"))
            url = urlsplit(target)
            if url.scheme or url.netloc or target.startswith("#"):
                continue
            relative = url.path
            if not relative: continue
            destination = path.parent / relative
            if not destination.resolve().is_relative_to(root):
                failures.append(f"{path}: link escapes checkout: {raw}")
                continue
            if not destination.exists():
                failures.append(f"{path}: missing link: {raw}")
                continue
            # Git names are canonical even if a case-insensitive worktree directory was
            # created with another spelling by a build tool. Untracked files use disk names.
            normalized = str(Path(os.path.normpath(destination)).relative_to(root))
            if normalized in tracked_names or any(p.startswith(normalized.rstrip("/") + "/") for p in tracked_names):
                continue
            if normalized.lower() in tracked_lower:
                failures.append(f"{path}: wrong-case link: {raw}")
                continue
            # macOS may resolve the wrong case; verify untracked spellings component by component.
            probe = path.parent
            for part in Path(relative).parts:
                if part == "..": probe = probe.parent
                elif part != ".":
                    if part not in {p.name for p in probe.iterdir()}:
                        failures.append(f"{path}: wrong-case link: {raw}")
                        break
                    probe = probe / part
    return failures
