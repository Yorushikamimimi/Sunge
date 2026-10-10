"""Test boundary failures that could overwrite or expose a private archive."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


initializer = load_module("init_vault", ROOT / "scripts/init_vault.py")
checker = load_module("check_public", ROOT / "scripts/check_public.py")


class PrivateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        shutil.copytree(ROOT / "templates", self.root / "templates")
        shutil.copyfile(ROOT / ".gitignore", self.root / ".gitignore")

    def tearDown(self):
        self.temp.cleanup()

    def test_creation_has_no_logs_and_is_not_trackable(self):
        initializer.initialize(self.root)
        vault = self.root / "local-vault"
        self.assertEqual({p.name for p in vault.iterdir()}, set(initializer.FILES))
        self.assertFalse((vault / "logs").exists())
        result = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain", "--untracked-files=all"],
            check=True, capture_output=True, text=True,
        )
        self.assertNotIn("local-vault/", result.stdout)

    def test_repeated_init_preserves_user_edits(self):
        initializer.initialize(self.root)
        path = self.root / "local-vault/PROFILE.md"
        path.write_text("虚构用户的修改，不得覆盖。", encoding="utf-8")
        before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
        initializer.initialize(self.root)
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.parent.iterdir()})

    def test_missing_ignore_refuses_any_private_write(self):
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            initializer.initialize(self.root)
        self.assertFalse((self.root / "local-vault").exists())

    def test_tracked_private_file_refuses_initialization(self):
        vault = self.root / "local-vault"
        vault.mkdir()
        path = vault / "PROFILE.md"
        path.write_text("虚构隔离探针", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "local-vault/PROFILE.md"], check=True)
        with self.assertRaises(ValueError):
            initializer.initialize(self.root)
        self.assertEqual(path.read_text(encoding="utf-8"), "虚构隔离探针")

    def test_symlink_and_partial_archive_refuse_without_overwrite(self):
        target = self.root / "fictional-target"
        target.mkdir()
        vault = self.root / "local-vault"
        vault.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            initializer.initialize(self.root)
        self.assertEqual(list(target.iterdir()), [])
        vault.unlink()  # Test-owned temporary link only.
        vault.mkdir()
        (vault / "notes.md").write_text("虚构已有内容", encoding="utf-8")
        with self.assertRaises(ValueError):
            initializer.initialize(self.root)
        self.assertEqual([p.name for p in vault.iterdir()], ["notes.md"])

    def test_public_checker_detects_private_canary_and_broken_links(self):
        # Reproduce the exact public set in a disposable repository.
        for name in checker.PUBLIC_FILES:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        self.assertEqual(checker.inspect(self.root), [])
        readme = self.root / "README.md"
        readme.write_text("[虚构坏链接](missing.md)\n" + "/" + "Users" + "/fictional/archive", encoding="utf-8")
        errors = checker.inspect(self.root)
        self.assertTrue(any("目标不存在" in x for x in errors))
        self.assertTrue(any("个人绝对路径" in x for x in errors))
        vault = self.root / "local-vault"
        vault.mkdir()
        (vault / "CANARY.md").write_text("虚构私密标记，不得公开", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "local-vault/CANARY.md"], check=True)
        self.assertTrue(any("公开清单之外" in x for x in checker.inspect(self.root)))


if __name__ == "__main__":
    unittest.main()
