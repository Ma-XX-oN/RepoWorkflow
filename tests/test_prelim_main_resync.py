"""Fast-forward only an inactive local main after verified integration."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.prelim_retirement import (
  PrelimRetirementError, RetirementPlan,
)
from repo_workflow.prelim_main_resync import resync_inactive_main

P = ("refs/heads/PRELIM-issue-123/main-"
     "11111111-1111-4111-8111-111111111111")
I = ("refs/heads/INT-ATTEMPT-issue-123/main-"
     "22222222-2222-4222-8222-222222222222")


def git(root, *args):
  value = subprocess.run(["git", "-C", str(root), *args],
    capture_output=True, text=True, check=True)
  return value.stdout.strip()


class MainResyncTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.local = root / "work"
    self.remote = root / "server.git"
    subprocess.run(["git", "init", "--bare", str(self.remote)],
      capture_output=True, check=True)
    subprocess.run(["git", "init", "-b", "main", str(self.local)],
      capture_output=True, check=True)
    git(self.local, "config", "user.name", "RWF Fixture")
    git(self.local, "config", "user.email", "fixture@example.invalid")
    (self.local / "file").write_text("A\n")
    git(self.local, "add", "file")
    git(self.local, "commit", "-m", "A")
    self.a = git(self.local, "rev-parse", "HEAD")
    git(self.local, "remote", "add", "origin", str(self.remote))
    git(self.local, "push", "origin", "main")
    git(self.local, "checkout", "-b", "feature")
    (self.local / "file").write_text("B\n")
    git(self.local, "commit", "-am", "B")
    self.b = git(self.local, "rev-parse", "HEAD")
    git(self.local, "push", "origin", self.b + ":refs/heads/main")
    self.plan = RetirementPlan(P, I, self.b, "terminal-1", True)

  def local_main(self):
    return git(self.local, "rev-parse", "refs/heads/main")

  def test_inactive_main_fast_forwards_and_preserves_worktree(self):
    before = git(self.local, "rev-parse", "HEAD")
    result = resync_inactive_main(self.local, "origin", self.plan)
    self.assertTrue(result.changed)
    self.assertEqual(self.local_main(), self.b)
    self.assertEqual(git(self.local, "rev-parse", "HEAD"), before)

  def test_resync_idempotent(self):
    resync_inactive_main(self.local, "origin", self.plan)
    second = resync_inactive_main(self.local, "origin", self.plan)
    self.assertFalse(second.changed)

  def test_checked_out_main_not_force_moved(self):
    git(self.local, "checkout", "main")
    with self.assertRaisesRegex(PrelimRetirementError, "checked out"):
      resync_inactive_main(self.local, "origin", self.plan)
    self.assertEqual(self.local_main(), self.a)

  def test_incomplete_plan_cannot_resync(self):
    with self.assertRaises(PrelimRetirementError):
      resync_inactive_main(
        self.local, "origin",
        replace(self.plan, eligible_for_ref_retirement=False))
    self.assertEqual(self.local_main(), self.a)

  def test_unlanded_sha_cannot_resync(self):
    with self.assertRaisesRegex(PrelimRetirementError, "not proved"):
      resync_inactive_main(self.local, "origin",
        replace(self.plan, landed_sha="e"*40))
    self.assertEqual(self.local_main(), self.a)

  def test_diverged_local_main_is_not_overwritten(self):
    git(self.local, "checkout", "main")
    (self.local / "other").write_text("C\\n")
    git(self.local, "add", "other")
    git(self.local, "commit", "-m", "independent main")
    original = self.local_main()
    git(self.local, "checkout", "feature")
    with self.assertRaisesRegex(PrelimRetirementError, "not proved"):
      resync_inactive_main(self.local, "origin", self.plan)
    self.assertEqual(self.local_main(), original)

  def test_main_checked_out_in_other_worktree_is_untouched(self):
    other = self.local.parent / "other-worktree"
    git(self.local, "worktree", "add", str(other), "main")
    with self.assertRaisesRegex(PrelimRetirementError, "checked out"):
      resync_inactive_main(self.local, "origin", self.plan)
    self.assertEqual(self.local_main(), self.a)

  def test_concurrent_local_main_move_fails_compare_and_swap(self):
    original_run = subprocess.run
    moved = [False]
    def competing_run(args, **kwargs):
      if (not moved[0] and len(args) > 4 and
          args[3] == "update-ref" and args[4] == "refs/heads/main"):
        moved[0] = True
        original_run(["git", "-C", str(self.local), "update-ref",
          "refs/heads/main", self.b, self.a], check=True,
          capture_output=True, text=True)
      return original_run(args, **kwargs)
    with patch("repo_workflow.prelim_main_resync.subprocess.run",
               side_effect=competing_run):
      with self.assertRaisesRegex(PrelimRetirementError, "concurrently"):
        resync_inactive_main(self.local, "origin", self.plan)
    self.assertTrue(moved[0])
    self.assertEqual(self.local_main(), self.b)

  def test_different_remote_is_not_accepted(self):
    with self.assertRaises(PrelimRetirementError):
      resync_inactive_main(self.local, "-bad", self.plan)
    self.assertEqual(self.local_main(), self.a)


if __name__ == "__main__":
  unittest.main()
