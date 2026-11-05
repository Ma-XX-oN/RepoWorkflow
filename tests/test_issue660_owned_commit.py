"""Real Git regression for selective durable command commits."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.owned_commit import OwnedCommitError, commit_owned_files


def git(root, *args):
  result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
  return result.stdout


class OwnedCommitTests(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.root = Path(tmp.name)
    git(self.root, "init", "-q")
    git(self.root, "config", "user.name", "Test")
    git(self.root, "config", "user.email", "test@example.invalid")
    for name in ("owned.txt", "unrelated.txt"):
      (self.root / name).write_text("zero\n", encoding="utf-8")
    git(self.root, "add", ".")
    git(self.root, "commit", "-qm", "initial")

  def test_preserves_unrelated_mixed_stage_and_worktree(self):
    (self.root / "unrelated.txt").write_text("staged\n")
    git(self.root, "add", "unrelated.txt")
    (self.root / "unrelated.txt").write_text("unstaged\n")
    staged_before = git(self.root, "show", ":unrelated.txt")
    unstaged_before = (self.root / "unrelated.txt").read_bytes()
    (self.root / "owned.txt").write_text("new\n")
    sha = commit_owned_files(self.root, ["owned.txt"], "owned change")
    self.assertEqual(sha, git(self.root, "rev-parse", "HEAD").decode().strip())
    self.assertEqual(git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), b"owned.txt\n")
    self.assertEqual(git(self.root, "show", ":unrelated.txt"), staged_before)
    self.assertEqual((self.root / "unrelated.txt").read_bytes(), unstaged_before)
    self.assertEqual(git(self.root, "status", "--short"), b"MM unrelated.txt\n")

  def test_empty_change_does_not_commit(self):
    before = git(self.root, "rev-parse", "HEAD")
    self.assertIsNone(commit_owned_files(self.root, ["owned.txt"], "no-op"))
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)

  def test_new_owned_file(self):
    (self.root / "new.txt").write_text("new\n", encoding="utf-8")
    commit_owned_files(self.root, ["new.txt"], "new record")
    self.assertEqual(git(self.root, "show", "HEAD:new.txt"), b"new\n")

  def test_delete_tracked_owned_file(self):
    (self.root / "owned.txt").unlink()
    commit_owned_files(self.root, ["owned.txt"], "remove owned file")
    self.assertEqual(git(self.root, "ls-tree", "HEAD", "--", "owned.txt"), b"")

  def test_owned_partial_stage_commits_worktree_and_preserves_unrelated_stage(self):
    (self.root / "owned.txt").write_text("partial-stage\n")
    git(self.root, "add", "owned.txt")
    (self.root / "owned.txt").write_text("complete-worktree\n")
    (self.root / "unrelated.txt").write_text("keep-staged\n")
    git(self.root, "add", "unrelated.txt")
    commit_owned_files(self.root, ["owned.txt"], "commit complete owned file")
    self.assertEqual(git(self.root, "show", "HEAD:owned.txt"), b"complete-worktree\n")
    self.assertEqual(git(self.root, "show", ":unrelated.txt"), b"keep-staged\n")
    self.assertEqual(git(self.root, "status", "--short"), b"M  unrelated.txt\n")

  def test_directory_path_cannot_commit_undeclared_tracked_files(self):
    directory = self.root / "owned-dir"
    directory.mkdir()
    source = directory / "nested.txt"
    source.write_text("original\n")
    git(self.root, "add", "owned-dir/nested.txt")
    git(self.root, "commit", "-qm", "register nested file")
    source.write_text("changed\n")
    before = git(self.root, "rev-parse", "HEAD")
    with self.assertRaises(OwnedCommitError):
      commit_owned_files(self.root, ["owned-dir"], "bad directory")
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
    self.assertEqual(git(self.root, "show", "HEAD:owned-dir/nested.txt"),
                     b"original\n")

  def test_rejects_path_escape_without_mutation(self):
    before = git(self.root, "rev-parse", "HEAD")
    with self.assertRaises(OwnedCommitError):
      commit_owned_files(self.root, ["../bad"], "bad")
    self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)


if __name__ == "__main__":
  unittest.main()
