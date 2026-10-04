from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.parent_branch import ParentRecoveryError, recover_parent


def run(root, *args):
  return subprocess.run(
    ["git", *args],
    cwd=root,
    text=True,
    capture_output=True,
    check=True,
  ).stdout.strip()


def commit(root, message):
  run(root, "commit", "--allow-empty", "-m", message)
  return run(root, "rev-parse", "HEAD")


class ParentRecoveryTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    run(self.repo, "init", "-b", "main")
    run(self.repo, "config", "user.email", "test@example.com")
    run(self.repo, "config", "user.name", "Test")
    commit(self.repo, "root")

  def tearDown(self):
    self.temp.cleanup()

  def identity(self, branch, parent):
    run(self.repo, "checkout", "-b", branch, parent)
    commit(
      self.repo,
      f"identity\n\nRWF-Branch: {branch}\nRWF-Parent: {parent}",
    )

  def test_nested_branch_ignores_inherited_marker(self):
    self.identity("lane-1", "main")
    self.identity("issue-2", "lane-1")
    self.assertEqual(recover_parent(self.repo, "issue-2"), "lane-1")

  def test_parent_advancement_and_equal_tip_ref_do_not_change_parent(self):
    self.identity("issue-2", "main")
    run(self.repo, "branch", "other", "main")
    run(self.repo, "checkout", "main")
    commit(self.repo, "advance")
    self.assertEqual(recover_parent(self.repo, "issue-2"), "main")

  def test_duplicate_matching_marker_fails_closed(self):
    self.identity("issue-2", "main")
    commit(
      self.repo,
      "later\n\nRWF-Branch: issue-2\nRWF-Parent: main",
    )
    with self.assertRaises(ParentRecoveryError):
      recover_parent(self.repo, "issue-2")

  def test_deleted_local_parent_with_remote_tracking_ref_recovers(self):
    self.identity("issue-2", "main")
    tip = run(self.repo, "rev-parse", "main")
    run(self.repo, "update-ref", "refs/remotes/origin/main", tip)
    run(self.repo, "branch", "-D", "main")
    self.assertEqual(recover_parent(self.repo, "issue-2"), "main")

  def test_missing_parent_representation_fails_closed(self):
    self.identity("issue-2", "main")
    run(self.repo, "branch", "-D", "main")
    with self.assertRaises(ParentRecoveryError):
      recover_parent(self.repo, "issue-2")


if __name__ == "__main__":
  unittest.main()
