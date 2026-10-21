"""Portable Markdown link and agent-entry-size checks."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def check(root, paths=None):
    root = Path(root).resolve()
    failures = []
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
            # macOS may resolve the wrong case; verify the spelling component by component.
            probe = path.parent
            for part in Path(relative).parts:
                if part == "..": probe = probe.parent
                elif part != ".":
                    if part not in {p.name for p in probe.iterdir()}:
                        failures.append(f"{path}: wrong-case link: {raw}")
                        break
                    probe = probe / part
    return failures
