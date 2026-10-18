"""Conditional cleanup refuses competing writer and unverified plan."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.prelim_retirement import (
  PrelimRetirementError, RetirementPlan,
)
from repo_workflow.prelim_retirement_remote import retire_verified_ref

P = ("refs/heads/PRELIM-issue-123/main-"
     "11111111-1111-4111-8111-111111111111")
I = ("refs/heads/INT-ATTEMPT-issue-123/main-"
     "22222222-2222-4222-8222-222222222222")


def git(root, *args):
  result = subprocess.run(["git", "-C", str(root), *args],
    capture_output=True, text=True, check=True)
  return result.stdout.strip()


class RemoteRetirementTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.root = root / "worker"
    self.remote = root / "remote.git"
    subprocess.run(["git", "init", "--bare", str(self.remote)],
      capture_output=True, check=True)
    subprocess.run(["git", "init", "-b", "main", str(self.root)],
      capture_output=True, check=True)
    git(self.root, "config", "user.name", "RWF Retirement Test")
    git(self.root, "config", "user.email", "test@example.invalid")
    (self.root / "file").write_text("A\n")
    git(self.root, "add", "file")
    git(self.root, "commit", "-m", "A")
    self.a = git(self.root, "rev-parse", "HEAD")
    git(self.root, "remote", "add", "origin", str(self.remote))
    git(self.root, "push", "origin", self.a + ":" + P)
    git(self.root, "push", "origin", self.a + ":" + I)
    (self.root / "file").write_text("B\n")
    git(self.root, "commit", "-am", "B")
    self.b = git(self.root, "rev-parse", "HEAD")
    self.plan = RetirementPlan(P, I, self.a, "terminal-123", True)

  def remote_sha(self, ref):
    result = git(self.root, "ls-remote", "origin", ref)
    return result.split()[0] if result else None

  def test_only_this_verified_attempt_ref_is_deleted(self):
    result = retire_verified_ref(self.root, "origin", self.plan, P, self.a)
    self.assertTrue(result.absent_after)
    self.assertIsNone(self.remote_sha(P))
    self.assertEqual(self.remote_sha(I), self.a)

  def test_stale_ref_is_not_deleted(self):
    git(self.root, "push", "--force", "origin", self.b + ":" + P)
    with self.assertRaises(PrelimRetirementError):
      retire_verified_ref(self.root, "origin", self.plan, P, self.a)
    self.assertEqual(self.remote_sha(P), self.b)

  def test_duplicate_retirement_is_not_reported_as_new(self):
    retire_verified_ref(self.root, "origin", self.plan, P, self.a)
    with self.assertRaises(PrelimRetirementError):
      retire_verified_ref(self.root, "origin", self.plan, P, self.a)

  def test_unverified_plan_cannot_delete(self):
    with self.assertRaises(PrelimRetirementError):
      retire_verified_ref(self.root, "origin",
        replace(self.plan, eligible_for_ref_retirement=False), P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_foreign_attempt_cannot_be_retired(self):
    with self.assertRaises(PrelimRetirementError):
      retire_verified_ref(self.root, "origin",
        replace(self.plan, int_attempt_ref=I.replace("issue-123", "issue-999")),
        P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_unrelated_ref_cannot_be_retired(self):
    with self.assertRaises(PrelimRetirementError):
      retire_verified_ref(self.root, "origin", self.plan,
        "refs/heads/main", self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_both_attempt_refs_require_separate_exact_sha(self):
    retire_verified_ref(self.root, "origin", self.plan, I, self.a)
    self.assertIsNone(self.remote_sha(I))
    self.assertEqual(self.remote_sha(P), self.a)


if __name__ == "__main__":
  unittest.main()
