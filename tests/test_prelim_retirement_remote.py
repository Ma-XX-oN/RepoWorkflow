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


class BoundBackend:
  """Stand-in for a repository-scoped, authenticated provider readback."""
  repository = "example/retirement-fixture"
  server_repository = "example/retirement-fixture"

  def __init__(self, url):
    self.url = str(url)

  def get(self, route):
    if route != "":
      raise AssertionError("unexpected provider route")
    return {"full_name": self.server_repository, "clone_url": self.url}


class RemoteRetirementTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    root = Path(self.tmp.name)
    self.root = root / "worker"
    self.remote = root / "remote.git"
    self.backend = BoundBackend(self.remote)
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

  def retire(self, plan, ref, sha, *, remote="origin"):
    return retire_verified_ref(self.root, remote, plan, ref, sha,
      backend=self.backend)

  def remote_sha(self, ref):
    result = git(self.root, "ls-remote", "origin", ref)
    return result.split()[0] if result else None

  def test_only_this_verified_attempt_ref_is_deleted(self):
    result = self.retire(self.plan, P, self.a)
    self.assertTrue(result.absent_after)
    self.assertIsNone(self.remote_sha(P))
    self.assertEqual(self.remote_sha(I), self.a)

  def test_generic_umbrella_ref_is_retired_only_with_its_pair(self):
    p=P.replace("issue-123", "team-X")
    i=I.replace("issue-123", "team-X")
    git(self.root, "push", "origin", self.a + ":" + p)
    git(self.root, "push", "origin", self.a + ":" + i)
    plan=RetirementPlan(p,i,self.a,"terminal-team-X",True)
    self.assertTrue(retire_verified_ref(
      self.root, "origin", plan, p, self.a, backend=self.backend).absent_after)
    self.assertIsNone(self.remote_sha(p))
    self.assertEqual(self.remote_sha(i),self.a)
    self.assertEqual(self.remote_sha(P),self.a)

  def test_stale_ref_is_not_deleted(self):
    git(self.root, "push", "--force", "origin", self.b + ":" + P)
    with self.assertRaises(PrelimRetirementError):
      self.retire(self.plan, P, self.a)
    self.assertEqual(self.remote_sha(P), self.b)

  def test_duplicate_retirement_is_not_reported_as_new(self):
    self.retire(self.plan, P, self.a)
    with self.assertRaises(PrelimRetirementError):
      self.retire(self.plan, P, self.a)

  def test_unverified_plan_cannot_delete(self):
    with self.assertRaises(PrelimRetirementError):
      self.retire(replace(self.plan, eligible_for_ref_retirement=False), P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_foreign_attempt_cannot_be_retired(self):
    with self.assertRaises(PrelimRetirementError):
      self.retire(replace(self.plan, int_attempt_ref=I.replace("issue-123", "issue-999")),
        P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_unrelated_ref_cannot_be_retired(self):
    with self.assertRaises(PrelimRetirementError):
      self.retire(self.plan,
        "refs/heads/main", self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_both_attempt_refs_require_separate_exact_sha(self):
    self.retire(self.plan, I, self.a)
    self.assertIsNone(self.remote_sha(I))
    self.assertEqual(self.remote_sha(P), self.a)

  def test_other_repository_with_identical_ref_and_sha_is_rejected(self):
    foreign = Path(self.tmp.name) / "foreign.git"
    subprocess.run(["git", "init", "--bare", str(foreign)],
      capture_output=True, check=True)
    git(self.root, "remote", "add", "foreign", str(foreign))
    git(self.root, "push", "foreign", self.a + ":" + P)
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      self.retire(self.plan, P, self.a, remote="foreign")
    self.assertEqual(self.remote_sha(P), self.a)
    self.assertEqual(git(self.root, "ls-remote", "foreign", P).split()[0],
      self.a)

  def test_retargeted_origin_is_rejected_before_deletion(self):
    foreign = Path(self.tmp.name) / "foreign.git"
    subprocess.run(["git", "init", "--bare", str(foreign)],
      capture_output=True, check=True)
    git(self.root, "push", str(foreign), self.a + ":" + P)
    git(self.root, "remote", "set-url", "origin", str(foreign))
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      self.retire(self.plan, P, self.a)
    git(self.root, "remote", "set-url", "origin", str(self.remote))
    self.assertEqual(self.remote_sha(P), self.a)
    self.assertEqual(git(self.root, "ls-remote", str(foreign), P).split()[0],
      self.a)

  def test_separate_push_url_is_rejected(self):
    foreign = Path(self.tmp.name) / "foreign.git"
    subprocess.run(["git", "init", "--bare", str(foreign)],
      capture_output=True, check=True)
    git(self.root, "remote", "set-url", "--push", "origin", str(foreign))
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      self.retire(self.plan, P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_git_instead_of_rewrite_to_foreign_is_rejected(self):
    foreign = Path(self.tmp.name) / "foreign.git"
    subprocess.run(["git", "init", "--bare", str(foreign)],
      capture_output=True, check=True)
    git(self.root, "config", "url."+str(foreign)+".insteadOf",
      str(self.remote))
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      self.retire(self.plan, P, self.a)
    git(self.root, "config", "--unset", "url."+str(foreign)+".insteadOf")
    self.assertEqual(self.remote_sha(P), self.a)

  def test_incorrect_provider_repository_is_rejected(self):
    self.backend.repository = "example/other"
    with self.assertRaisesRegex(PrelimRetirementError, "identity mismatch"):
      self.retire(self.plan, P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_missing_authenticated_backend_is_rejected(self):
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      retire_verified_ref(self.root, "origin", self.plan, P, self.a,
        backend=None)
    self.assertEqual(self.remote_sha(P), self.a)


if __name__ == "__main__":
  unittest.main()
