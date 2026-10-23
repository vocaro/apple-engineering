"""Portable Markdown link, anchor and agent-entry-size checks."""
import html
from pathlib import Path
import re
import os
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

MARKDOWN = {".md", ".markdown"}
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
ATX = re.compile(r" {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
SETEXT = re.compile(r" {0,3}(?:=+|-+)[ \t]*$")
BREAK = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
# Lines that open a block other than a paragraph, which no setext underline turns into a heading.
OTHER_BLOCK = re.compile(r" {4}|\t| {0,3}(?:[-*+][ \t]|\d{1,9}[.)][ \t]|[>|<])")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
HTML_ANCHOR = re.compile(r"<[A-Za-z][^>]*?\s(?:id|name)\s*=\s*([\"'])(.*?)\1")


def slug(text):
    """GitHub's heading anchor: lowercase, keeping only word characters, hyphens and spaces, and
    each space a hyphen. Word characters are letters, marks, decimal digits and connectors (_)."""
    return "".join("-" if c == " " else c for c in text.lower()
                   if c in " -" or unicodedata.category(c)[0] in "LM" or unicodedata.category(c) in ("Nd", "Pc"))


def heading_text(source):
    """A heading's text as GitHub renders it: code spans verbatim, link and emphasis markup gone."""
    def inline(text):
        text = re.sub(r"!?\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])", r"\1", text)
        text = re.sub(r"<[^>]*>", "", text)
        text = re.sub(r"(?<![\w\\])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)
        return html.unescape(re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text))
    pieces, last = [], 0
    for span in CODE_SPAN.finditer(source):
        code = span[2]
        if code.startswith(" ") and code.endswith(" ") and code.strip(): code = code[1:-1]
        pieces += [inline(source[last:span.start()]), code]
        last = span.end()
    return "".join(pieces + [inline(source[last:])]).strip()


def anchors(text):
    """The fragments GitHub defines for a Markdown document: heading slugs and HTML ids."""
    found, occurrences = set(), {}
    def heading(source):
        base = slug(heading_text(source))
        if not base: return
        name = base
        while name in occurrences:  # a repeated heading gets -1, -2, as GitHub numbers them
            occurrences[base] += 1
            name = f"{base}-{occurrences[base]}"
        occurrences[name] = 0
        found.add(name)
    fence, paragraph = None, []
    for line in text.splitlines():
        if fence:
            if re.match(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line): fence = None
            continue
        opening = FENCE.match(line)
        if opening:
            fence, paragraph = opening[1], []
            continue
        found.update(match[2] for match in HTML_ANCHOR.finditer(CODE_SPAN.sub("", line)))
        atx = ATX.match(line)
        if not line.strip(): paragraph = []
        elif paragraph and SETEXT.match(line): heading("\n".join(paragraph)); paragraph = []
        elif atx: heading(atx[1] or ""); paragraph = []
        elif BREAK.match(line): paragraph = []
        elif OTHER_BLOCK.match(line): paragraph = None   # until the next blank line
        elif paragraph is not None: paragraph.append(line.strip())
    return found


def check(root, paths=None):
    root = Path(root).resolve()
    failures = []
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, timeout=30)
    tracked_names = {os.fsdecode(p) for p in tracked.stdout.split(b"\0") if p}
    tracked_lower = {p.lower() for p in tracked_names}
    defined = {}
    def missing_anchor(document, fragment):
        if document not in defined: defined[document] = anchors(document.read_text())
        return fragment not in defined[document]
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
            if url.scheme or url.netloc:
                continue
            if target.startswith("#"):
                if url.fragment and missing_anchor(path.resolve(), url.fragment):
                    failures.append(f"{path}: missing anchor: {raw}")
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
            # Only a Markdown target's fragments are known here; a source line's (#L10) is not.
            if (url.fragment and not url.query and destination.suffix.lower() in MARKDOWN
                    and destination.is_file() and missing_anchor(destination.resolve(), url.fragment)):
                failures.append(f"{path}: missing anchor: {raw}")
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
