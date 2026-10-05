from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


def bash_path(path: Path) -> str:
  value = path.resolve().as_posix()
  if os.name == "nt" and len(value) >= 3 and value[1:3] == ":/":
    value = f"/{value[0].lower()}{value[2:]}"
  return value


class PublicBashInitTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "--allow-empty", "-m", "initial"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )

  def run_cli(self, root: Path):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), "init", "bash"],
      capture_output=True,
      text=True,
    )

  def test_no_workflow_config_required_and_nested_root_is_resolved(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      nested = root / "a" / "b"
      nested.mkdir(parents=True)
      self.make_repo(root)
      (root / "rwf").write_text("#!/bin/sh\n", encoding="utf-8")
      (root / "repo_workflow.py").write_text("", encoding="utf-8")

      before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      ).stdout
      completed = self.run_cli(nested)
      after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      ).stdout

      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertNotIn("repoworkflow.json", completed.stderr)
      self.assertIn(root.resolve().as_posix(), completed.stdout)
      self.assertNotIn(nested.resolve().as_posix(), completed.stdout)
      self.assertEqual(after, before)
      self.assertFalse((root / ".repoworkflow").exists())

  def test_outside_repository_fails_actionably(self):
    with tempfile.TemporaryDirectory() as td:
      completed = self.run_cli(Path(td))

      self.assertEqual(completed.returncode, 2)
      self.assertIn("not inside a suitable Git working tree", completed.stderr)
      self.assertNotIn("Traceback (most recent call last)", completed.stderr)


if __name__ == "__main__":
  unittest.main()
