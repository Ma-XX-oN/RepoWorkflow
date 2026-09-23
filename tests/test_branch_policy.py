from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from repo_workflow.branch_policy import BranchPolicyError, check_branch_policy


class BranchPolicyTests(unittest.TestCase):
  def git(self, root: Path, *args: str, check=True):
    return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True, text=True)

  def make_repo(self):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    remote = Path(td.name) / "remote.git"
    root.mkdir()
    self.git(root, "init", "-b", "main")
    self.git(root, "config", "user.name", "Test")
    self.git(root, "config", "user.email", "test@example.invalid")
    (root / "base.txt").write_text("base\n")
    self.git(root, "add", ".")
    self.git(root, "commit", "-m", "base")
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    self.git(root, "remote", "add", "origin", str(remote))
    self.git(root, "push", "-u", "origin", "main")
    (root / ".ci").mkdir()
    return td, root

  def write_policy(self, root: Path, *, branches=None, patterns=None):
    (root / ".ci" / "branch-policy.json").write_text(json.dumps({
      "schema": 1,
      "integrationBranch": "main",
      "branches": branches or {},
      "patterns": patterns or [],
    }))

  def branch_commit(self, root: Path, branch: str, filename: str):
    self.git(root, "switch", "-c", branch)
    (root / filename).write_text(branch + "\n")
    self.git(root, "add", ".")
    self.git(root, "commit", "-m", branch)
    self.git(root, "push", "-u", "origin", branch)

  def test_normal_issue_branch_from_main_passes(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, patterns=[{
        "pattern": "issue-*", "parent": "main", "allowedDependencies": []
      }])
      self.branch_commit(root, "issue-1-test", "issue.txt")
      check_branch_policy(root, "issue-1-test", None, "origin")

  def test_wrong_pr_base_is_rejected(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, branches={
        "issue-1-test": {"parent": "main", "allowedDependencies": []}
      })
      self.branch_commit(root, "issue-1-test", "issue.txt")
      with self.assertRaisesRegex(BranchPolicyError, "pull request base"):
        check_branch_policy(root, "issue-1-test", "other", "origin")

  def test_undeclared_dependency_merge_is_rejected(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, branches={
        "issue-1-test": {"parent": "main", "allowedDependencies": []}
      })
      self.branch_commit(root, "issue-2-dependency", "dep.txt")
      self.git(root, "switch", "main")
      self.git(root, "switch", "-c", "issue-1-test")
      self.git(root, "merge", "--no-ff", "issue-2-dependency", "-m", "merge dep")
      self.git(root, "push", "-u", "origin", "issue-1-test")
      with self.assertRaisesRegex(BranchPolicyError, "undeclared history"):
        check_branch_policy(root, "issue-1-test", None, "origin")

  def test_declared_dependency_merge_passes(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, branches={
        "issue-1-test": {
          "parent": "main", "allowedDependencies": ["issue-2-dependency"]
        }
      })
      self.branch_commit(root, "issue-2-dependency", "dep.txt")
      self.git(root, "switch", "main")
      self.git(root, "switch", "-c", "issue-1-test")
      self.git(root, "merge", "--no-ff", "issue-2-dependency", "-m", "merge dep")
      self.git(root, "push", "-u", "origin", "issue-1-test")
      check_branch_policy(root, "issue-1-test", None, "origin")

  def test_integration_target_controls_pr_base(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, branches={
        "feature/integration": {
          "parent": "main", "umbrella": True,
          "integrationTarget": "main", "allowedDependencies": ["issue-2-dependency"]
        }
      })
      self.branch_commit(root, "feature/integration", "feature.txt")
      check_branch_policy(root, "feature/integration", "main", "origin")

  def test_umbrella_rule_requires_target_and_children(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root, branches={
        "feature/integration": {"parent": "main", "umbrella": True}
      })
      self.branch_commit(root, "feature/integration", "feature.txt")
      with self.assertRaises(BranchPolicyError):
        check_branch_policy(root, "feature/integration", None, "origin")

  def test_unmatched_branch_is_rejected(self):
    td, root = self.make_repo()
    with td:
      self.write_policy(root)
      self.branch_commit(root, "mystery", "x.txt")
      with self.assertRaisesRegex(BranchPolicyError, "no branch policy rule"):
        check_branch_policy(root, "mystery", None, "origin")


if __name__ == "__main__":
  unittest.main()
