from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.workspace_worktree import (
  WorktreeBackend,
  WorktreeError,
)


def run_git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", *args],
    cwd=root,
    text=True,
    capture_output=True,
    check=True,
  )
  return result.stdout.strip()


class WorktreeBackendTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.base = Path(self.temp.name)
    self.root = self.base / "repo"
    self.root.mkdir()
    run_git(self.root, "init")
    run_git(self.root, "config", "user.email", "rwf@example.test")
    run_git(self.root, "config", "user.name", "RWF Test")
    (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
    run_git(self.root, "add", "seed.txt")
    run_git(self.root, "commit", "-m", "seed")
    self.main_branch = run_git(
      self.root,
      "rev-parse",
      "--abbrev-ref",
      "HEAD",
    )
    self.base_sha = run_git(self.root, "rev-parse", "HEAD")
    self.backend = WorktreeBackend(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_provision_creates_exact_branch_and_worktree(self):
    path = self.base / "RWF-89"
    info = self.backend.provision(
      workspace_id="RWF-89",
      base_ref=self.main_branch,
      base_sha=self.base_sha,
      branch_name="issue-89-version-contract",
      worktree_path=path,
    )

    self.assertEqual(info.workspace_id, "RWF-89")
    self.assertEqual(info.path, path.resolve())
    self.assertEqual(info.branch, "issue-89-version-contract")
    self.assertEqual(info.head, self.base_sha)
    self.assertEqual(run_git(path, "rev-parse", "HEAD"), self.base_sha)
    self.assertEqual(
      run_git(path, "rev-parse", "--abbrev-ref", "HEAD"),
      "issue-89-version-contract",
    )

  def test_multiple_independent_worktrees_can_coexist(self):
    first = self.backend.provision(
      "RWF-89",
      self.main_branch,
      self.base_sha,
      "issue-89-version-contract",
      self.base / "RWF-89",
    )
    second = self.backend.provision(
      "RWF-77",
      self.main_branch,
      self.base_sha,
      "issue-77-relationships",
      self.base / "RWF-77",
    )

    self.assertNotEqual(first.path, second.path)
    self.assertTrue(first.path.is_dir())
    self.assertTrue(second.path.is_dir())

  def test_stale_symbolic_base_is_rejected(self):
    (self.root / "advance.txt").write_text("advance\n", encoding="utf-8")
    run_git(self.root, "add", "advance.txt")
    run_git(self.root, "commit", "-m", "advance")

    with self.assertRaisesRegex(WorktreeError, "stale base"):
      self.backend.provision(
        "RWF-89",
        self.main_branch,
        self.base_sha,
        "issue-89-version-contract",
        self.base / "RWF-89",
      )

    self.assertFalse((self.base / "RWF-89").exists())
    self.assertNotIn(
      "refs/heads/issue-89-version-contract",
      run_git(self.root, "show-ref"),
    )

  def test_existing_path_is_rejected_without_mutation(self):
    path = self.base / "RWF-89"
    path.mkdir()
    (path / "unrelated.txt").write_text("keep\n", encoding="utf-8")

    with self.assertRaisesRegex(WorktreeError, "path already exists"):
      self.backend.provision(
        "RWF-89",
        self.main_branch,
        self.base_sha,
        "issue-89-version-contract",
        path,
      )

    self.assertEqual(
      (path / "unrelated.txt").read_text(encoding="utf-8"),
      "keep\n",
    )

  def test_existing_branch_is_rejected_without_explicit_reuse(self):
    run_git(
      self.root,
      "branch",
      "issue-89-version-contract",
      self.base_sha,
    )

    with self.assertRaisesRegex(WorktreeError, "branch already exists"):
      self.backend.provision(
        "RWF-89",
        self.main_branch,
        self.base_sha,
        "issue-89-version-contract",
        self.base / "RWF-89",
      )

  def test_retire_refuses_uncommitted_work(self):
    path = self.base / "RWF-89"
    self.backend.provision(
      "RWF-89",
      self.main_branch,
      self.base_sha,
      "issue-89-version-contract",
      path,
    )
    (path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    with self.assertRaisesRegex(WorktreeError, "protected local work"):
      self.backend.retire(
        "RWF-89",
        path,
        "issue-89-version-contract",
      )

    self.assertTrue(path.is_dir())

  def test_retire_clean_worktree_preserves_branch_by_default(self):
    path = self.base / "RWF-89"
    self.backend.provision(
      "RWF-89",
      self.main_branch,
      self.base_sha,
      "issue-89-version-contract",
      path,
    )

    self.backend.retire(
      "RWF-89",
      path,
      "issue-89-version-contract",
    )

    self.assertFalse(path.exists())
    self.assertEqual(
      run_git(
        self.root,
        "rev-parse",
        "refs/heads/issue-89-version-contract",
      ),
      self.base_sha,
    )

  def test_retire_can_delete_explicitly_disposable_branch(self):
    path = self.base / "RWF-89"
    self.backend.provision(
      "RWF-89",
      self.main_branch,
      self.base_sha,
      "issue-89-version-contract",
      path,
    )

    self.backend.retire(
      "RWF-89",
      path,
      "issue-89-version-contract",
      delete_branch=True,
    )

    result = subprocess.run(
      [
        "git",
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/issue-89-version-contract",
      ],
      cwd=self.root,
      check=False,
    )
    self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
  unittest.main()
