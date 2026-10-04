from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.parent_branch import ParentBranchError, recover_parent_branch


class ParentBranchRecoveryTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
    (self.root / "base").write_text("base")
    self.git("add", "base")
    self.git("commit", "-m", "base")

  def tearDown(self):
    self.temp.cleanup()

  def git(self, *args):
    return subprocess.run(
      ["git", *args], cwd=self.root, text=True, capture_output=True, check=True
    ).stdout.strip()

  def identity(self, branch, parent):
    self.git("checkout", "-b", branch, parent)
    self.git(
      "commit", "--allow-empty", "-m",
      f"RWF identity\n\nRWF-Branch: {branch}\nRWF-Parent: {parent}",
    )

  def test_parent_advancement_and_equal_tip_sibling_do_not_change_parent(self):
    self.identity("issue-10", "main")
    self.git("branch", "same-tip")
    self.git("checkout", "main")
    (self.root / "advance").write_text("advance")
    self.git("add", "advance")
    self.git("commit", "-m", "advance")

    self.assertEqual(recover_parent_branch(self.root, "issue-10"), "main")

  def test_nested_branch_ignores_inherited_parent_marker(self):
    self.identity("lane-20", "main")
    self.identity("issue-21", "lane-20")

    self.assertEqual(recover_parent_branch(self.root, "issue-21"), "lane-20")

  def test_remote_tracking_parent_survives_deleted_local_ref(self):
    self.identity("issue-10", "main")
    main = self.git("rev-parse", "main")
    self.git("update-ref", "refs/remotes/origin/main", main)
    self.git("branch", "-D", "main")

    self.assertEqual(recover_parent_branch(self.root, "issue-10"), "main")

  def test_duplicate_matching_marker_fails_closed(self):
    self.identity("issue-10", "main")
    self.git(
      "commit", "--allow-empty", "-m",
      "bad duplicate\n\nRWF-Branch: issue-10\nRWF-Parent: main",
    )

    with self.assertRaisesRegex(ParentBranchError, "exactly one"):
      recover_parent_branch(self.root, "issue-10")

  def test_rewritten_parent_fails_closed(self):
    self.identity("issue-10", "main")
    self.git("checkout", "--orphan", "replacement")
    (self.root / "replacement").write_text("replacement")
    self.git("add", "replacement")
    self.git("commit", "-m", "replacement")
    replacement = self.git("rev-parse", "HEAD")
    self.git("update-ref", "refs/heads/main", replacement)

    with self.assertRaisesRegex(ParentBranchError, "no longer contains"):
      recover_parent_branch(self.root, "issue-10")


  def test_remote_only_work_and_parent_refs_recover_in_fetched_clone(self):
    self.identity("issue-10", "main")
    work = self.git("rev-parse", "issue-10")
    parent = self.git("rev-parse", "main")
    self.git("update-ref", "refs/remotes/origin/issue-10", work)
    self.git("update-ref", "refs/remotes/origin/main", parent)
    self.git("checkout", "--detach", work)
    self.git("branch", "-D", "issue-10")
    self.git("branch", "-D", "main")

    self.assertEqual(recover_parent_branch(self.root, "issue-10"), "main")

  def test_conflicting_same_name_work_refs_fail_closed(self):
    self.identity("issue-10", "main")
    parent = self.git("rev-parse", "main")
    self.git("update-ref", "refs/remotes/origin/issue-10", parent)

    with self.assertRaisesRegex(ParentBranchError, "conflicting"):
      recover_parent_branch(self.root, "issue-10")


if __name__ == "__main__":
  unittest.main()
