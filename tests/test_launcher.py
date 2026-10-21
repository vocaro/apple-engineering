import contextlib
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/python"))
from vocaro_engineering import cli, config

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "core.hooksPath=/dev/null",
       "-c", "commit.gpgSign=false", "-c", "init.defaultBranch=main"]


def shared_adapter():
    spec = importlib.util.spec_from_file_location("_engineering_under_test", config.TOOLKIT_ROOT / "integrations/shared.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorktreeLauncherTests(unittest.TestCase):
    """A session worktree under <repo>/.claude/worktrees has no toolkit clone beside it."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.main = self.base / "Project"
        self.main.mkdir()
        (self.main / "engineering.json").write_text(json.dumps({"schemaVersion": 1, "name": "Project"}))
        with contextlib.redirect_stdout(StringIO()):
            cli.main(["--project", str(self.main), "init"])
        subprocess.run([*GIT, "init", "-q", str(self.main)], check=True)
        subprocess.run([*GIT, "-C", str(self.main), "add", "engineering.json", "scripts/eng", "scripts/_engineering.py"], check=True)
        subprocess.run([*GIT, "-C", str(self.main), "commit", "-q", "-m", "Adopt"], check=True)
        self.worktree = self.main / ".claude/worktrees/session"
        subprocess.run([*GIT, "-C", str(self.main), "worktree", "add", "-q", "-b", "session", str(self.worktree)], check=True)
        self.environment = {key: value for key, value in os.environ.items() if key != "VOCARO_ENGINEERING_ROOT"}
        self.environment["PATH"] = str(Path(sys.executable).parent)

    def provision(self, beside):
        (beside / "apple-engineering").symlink_to(config.TOOLKIT_ROOT, target_is_directory=True)

    def launch(self, checkout, **environment):
        return subprocess.run([sys.executable, str(checkout / "scripts/eng"), "instructions"],
                              capture_output=True, text=True, env={**self.environment, **environment})

    def test_init_installs_the_adapter_the_launcher_imports(self):
        self.assertTrue((self.main / "scripts/_engineering.py").is_file())
        self.assertEqual((self.main / "scripts/_engineering.py").read_bytes(),
                         (config.TOOLKIT_ROOT / "integrations/shared.py").read_bytes())

    def test_worktree_launcher_finds_the_clone_beside_the_main_checkout(self):
        self.provision(self.base)
        self.assertFalse((self.worktree.parent / "apple-engineering").exists())
        result = self.launch(self.worktree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Common engineering rules", result.stdout)
        adapter = shared_adapter()
        self.assertEqual(adapter.main_checkout(self.worktree), self.main)
        self.assertEqual(adapter.toolkit_location(self.worktree), config.TOOLKIT_ROOT)

    def test_worktree_without_any_clone_names_the_main_checkout_sibling(self):
        result = self.launch(self.worktree)
        self.assertEqual(result.returncode, 2)
        self.assertIn(f"Shared toolkit missing at {self.base / 'apple-engineering'}", result.stderr)

    def test_main_checkout_does_not_fall_back(self):
        adapter = shared_adapter()
        self.assertIsNone(adapter.main_checkout(self.main))
        self.provision(self.base)
        self.assertEqual(self.launch(self.main).returncode, 0)

    def test_submodule_git_file_without_commondir_does_not_fall_back(self):
        submodule = self.base / "Submodule"
        (submodule / "git-private").mkdir(parents=True)
        (submodule / ".git").write_text("gitdir: git-private\n")
        self.assertIsNone(shared_adapter().main_checkout(submodule))

    def test_environment_override_wins_over_the_fallback(self):
        self.provision(self.base)
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        result = self.launch(self.worktree, VOCARO_ENGINEERING_ROOT=str(elsewhere))
        self.assertEqual(result.returncode, 2)
        self.assertIn(f"Shared toolkit missing at {elsewhere}", result.stderr)
        adapter = shared_adapter()
        with patch.dict(os.environ, {"VOCARO_ENGINEERING_ROOT": str(config.TOOLKIT_ROOT)}):
            self.assertEqual(adapter.toolkit_location(self.worktree), config.TOOLKIT_ROOT)

    def test_shared_scripts_load_the_toolkit_from_a_worktree(self):
        self.provision(self.base)
        script = self.worktree / "scripts/probe.py"
        script.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
                          "from _engineering import toolkit_root\nprint(toolkit_root(Path(__file__).parents[1]))\n"
                          "from vocaro_engineering import resources\n")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), config.TOOLKIT_ROOT)


if __name__ == "__main__":
    unittest.main()
