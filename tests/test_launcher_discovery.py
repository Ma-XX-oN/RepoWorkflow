from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from repo_workflow.launcher_discovery import (
  LauncherDiscoveryError,
  discover_repository_launcher,
)


class LauncherDiscoveryTests(unittest.TestCase):
  def make_repo(self, root: Path) -> str:
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
    return subprocess.run(
      ["git", "rev-parse", "HEAD"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    ).stdout.strip()

  def test_self_repository_discovery_works_from_nested_directory(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      nested = root / "a" / "b"
      nested.mkdir(parents=True)
      self.make_repo(root)
      (root / "rwf").write_text("#!/bin/sh\n", encoding="utf-8")
      (root / "repo_workflow.py").write_text("", encoding="utf-8")

      found = discover_repository_launcher(nested)

      self.assertEqual(found.repository_root, root.resolve())
      self.assertEqual(found.launcher, (root / "rwf").resolve())
      self.assertFalse(found.requires_python)

  def test_consumer_discovery_prefers_stable_pinned_launcher(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      commit = self.make_repo(root)
      scripts = root / "scripts"
      scripts.mkdir()
      stable = scripts / "repoworkflow.py"
      stable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
      (root / "rwf").write_text("#!/bin/sh\n", encoding="utf-8")
      (root / "repo_workflow.py").write_text("", encoding="utf-8")
      subprocess.run(
        [
          "git", "update-index", "--add", "--cacheinfo",
          f"160000,{commit},RepoWorkflow",
        ],
        cwd=root,
        check=True,
      )
      subprocess.run(
        ["git", "commit", "-m", "pin RepoWorkflow"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )

      found = discover_repository_launcher(root)

      self.assertEqual(found.launcher, stable.resolve())
      self.assertTrue(found.requires_python)

  def test_unpinned_consumer_launcher_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      scripts = root / "scripts"
      scripts.mkdir()
      (scripts / "repoworkflow.py").write_text("", encoding="utf-8")

      with self.assertRaisesRegex(
        LauncherDiscoveryError,
        "no repository-local RWF launcher",
      ):
        discover_repository_launcher(root)



  def test_regular_repoworkflow_directory_is_not_accepted_as_gitlink(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)
      scripts = root / "scripts"
      scripts.mkdir()
      (scripts / "repoworkflow.py").write_text("", encoding="utf-8")
      engine_dir = root / "RepoWorkflow"
      engine_dir.mkdir()
      (engine_dir / "README.md").write_text("not a submodule\n", encoding="utf-8")
      subprocess.run(
        ["git", "add", "scripts/repoworkflow.py", "RepoWorkflow/README.md"],
        cwd=root,
        check=True,
      )
      subprocess.run(
        ["git", "commit", "-m", "lookalike engine directory"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )

      with self.assertRaisesRegex(
        LauncherDiscoveryError,
        "no repository-local RWF launcher",
      ):
        discover_repository_launcher(root)


  def test_pinned_consumer_without_stable_launcher_is_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      commit = self.make_repo(root)
      subprocess.run(
        [
          "git", "update-index", "--add", "--cacheinfo",
          f"160000,{commit},RepoWorkflow",
        ],
        cwd=root,
        check=True,
      )
      subprocess.run(
        ["git", "commit", "-m", "pin RepoWorkflow"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      )

      with self.assertRaisesRegex(
        LauncherDiscoveryError,
        "no repository-local RWF launcher",
      ):
        discover_repository_launcher(root)


  def test_missing_git_fails_actionably(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      old_path = os.environ.get("PATH")
      try:
        os.environ["PATH"] = ""
        with self.assertRaisesRegex(
          LauncherDiscoveryError,
          "Git is required",
        ):
          discover_repository_launcher(root)
      finally:
        if old_path is None:
          os.environ.pop("PATH", None)
        else:
          os.environ["PATH"] = old_path


  def test_outside_git_repository_fails_actionably(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)

      with self.assertRaisesRegex(
        LauncherDiscoveryError,
        "not inside a suitable Git working tree",
      ):
        discover_repository_launcher(root)


if __name__ == "__main__":
  unittest.main()
