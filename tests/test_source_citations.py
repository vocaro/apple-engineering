from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = re.compile(r"\b((?:guides|knowledge)/[\w-]+\.md)#([\w-]+)")
# Project documents that are not in this repository: a citation of one does not resolve here.
PROJECT_DOCUMENT = re.compile(r"\bdoc/[\w-]+\.md\b|\bAGENTS\.md#")


def anchors(path):
    """GitHub's heading anchors: lower case, punctuation dropped, spaces as hyphens."""
    headings = re.findall(r"^#+\s+(.+?)\s*$", re.sub(r"```.*?```", "", path.read_text(), flags=re.S), re.M)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


def unresolved(text):
    failures = [f"project document: {match[0]}" for match in PROJECT_DOCUMENT.finditer(text)]
    for document, anchor in GUIDE.findall(text):
        path = ROOT / document
        if not path.is_file() or anchor not in anchors(path):
            failures.append(f"{document}#{anchor}")
    return failures


class SourceCitationTests(unittest.TestCase):
    def test_source_comments_cite_guides_that_exist_here(self):
        failures = {}
        for path in sorted((ROOT / "src").rglob("*")):
            if path.suffix in (".py", ".swift", ".m", ".h") and ".build" not in path.parts:
                found = unresolved(path.read_text(errors="replace"))
                if found:
                    failures[str(path.relative_to(ROOT))] = found
        self.assertEqual(failures, {})

    def test_the_check_rejects_missing_anchors_and_project_documents(self):
        self.assertEqual(unresolved("see guides/hosted-runner.md#sharing-the-runner"), [])
        self.assertEqual(unresolved("see guides/hosted-runner.md#the-hosted-runner"), ["guides/hosted-runner.md#the-hosted-runner"])
        self.assertEqual(unresolved("see guides/missing.md#purpose"), ["guides/missing.md#purpose"])
        self.assertEqual(unresolved('see "Sharing the runner" in doc/testing.md and AGENTS.md#the-hosted-runner'),
                         ["project document: doc/testing.md", "project document: AGENTS.md#"])


if __name__ == "__main__":
    unittest.main()
