"""Conditional cleanup refuses competing writer and unverified plan."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.prelim_retirement import (
  PrelimRetirementError, RetirementPlan, LandedIntegration,
)
from repo_workflow.prelim_retirement_remote import retire_verified_ref
from repo_workflow.prelim_retirement_execute import retire_landed_attempt_ref

P = ("refs/heads/PRELIM-issue-123/main-"
     "11111111-1111-4111-8111-111111111111")
I = ("refs/heads/INT-ATTEMPT-issue-123/main-"
     "22222222-2222-4222-8222-222222222222")


def git(root, *args):
  result = subprocess.run(["git", "-C", str(root), *args],
    capture_output=True, text=True, check=True)
  return result.stdout.strip()


class MissingRef(Exception):
  code = "not_found"


class BoundBackend:
  """Independent bare-repo-backed stand-in for authenticated GitHub facts."""
  repository = "example/retirement-fixture"
  server_repository = "example/retirement-fixture"

  def __init__(self, url):
    self.url = str(url)

  def get(self, route):
    if route == "":
      return {"full_name": self.server_repository, "clone_url": self.url}
    if route.startswith("git/ref/"):
      ref = "refs/" + route.removeprefix("git/ref/")
      out = subprocess.run(["git", "ls-remote", self.url, ref],
        capture_output=True, text=True, check=True).stdout.strip()
      if not out:
        raise MissingRef()
      return {"ref": ref, "object": {"sha": out.split()[0]}}
    if route.startswith("compare/"):
      base, head = route.removeprefix("compare/").split("...")
      status = "identical" if base == head else "diverged"
      return {"base_commit": {"sha": base},
              "merge_base_commit": {"sha": base if status == "identical" else "0"*40},
              "status": status, "behind_by": 0}
    raise AssertionError("unexpected provider route")


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
    git(self.root, "push", "origin", self.a + ":refs/heads/main")
    (self.root / "file").write_text("B\n")
    git(self.root, "commit", "-am", "B")
    self.b = git(self.root, "rev-parse", "HEAD")
    self.plan = RetirementPlan(P, I, self.a, "terminal-123", True)

  def evidence(self, plan):
    landed = LandedIntegration(plan.prelim_ref, self.a,
      plan.int_attempt_ref, self.a, "refs/heads/main", self.a,
      "op-123", plan.terminal_evidence_ref)
    terminal = {
      "status": "integrated", "prelim_ref": plan.prelim_ref,
      "prelim_sha": self.a, "int_attempt_ref": plan.int_attempt_ref,
      "accepted_sha": self.a, "destination_ref": "refs/heads/main",
      "landed_sha": self.a, "integration_id": "op-123",
      "terminal_evidence_ref": plan.terminal_evidence_ref,
    }
    return landed, lambda _: terminal

  def retire(self, plan, ref, sha, *, remote="origin"):
    landed, read_terminal = self.evidence(plan)
    return retire_verified_ref(self.root, remote, plan, ref, sha,
      backend=self.backend, landed=landed, read_terminal=read_terminal)

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
    self.assertTrue(self.retire(plan, p, self.a).absent_after)
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

  def test_sibling_attempt_with_same_sha_is_never_deleted(self):
    sibling = P.replace("11111111-1111-4111-8111-111111111111",
                        "99999999-9999-4999-8999-999999999999")
    sibling_int = I.replace("22222222-2222-4222-8222-222222222222",
                            "88888888-8888-4888-8888-888888888888")
    git(self.root, "push", "origin", self.a + ":" + sibling)
    git(self.root, "push", "origin", self.a + ":" + sibling_int)
    result = self.retire(self.plan, P, self.a)
    self.assertTrue(result.absent_after)
    self.assertIsNone(self.remote_sha(P))
    self.assertEqual(self.remote_sha(I), self.a)
    self.assertEqual(self.remote_sha(sibling), self.a)
    self.assertEqual(self.remote_sha(sibling_int), self.a)

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

  def test_orchestrator_rechecks_live_terminal_at_delete_boundary(self):
    landed, terminal = self.evidence(self.plan)
    calls = [0]
    def changing_result(identity):
      calls[0] += 1
      return terminal(identity) if calls[0] == 1 else None
    with self.assertRaisesRegex(PrelimRetirementError, "terminal evidence"):
      retire_landed_attempt_ref(root=self.root, remote="origin",
        backend=self.backend, landed=landed,
        read_terminal=changing_result, ref_kind="PRELIM")
    self.assertEqual(calls[0], 2)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_orchestrator_landed_cleanup_uses_twice_read_terminal(self):
    landed, terminal = self.evidence(self.plan)
    calls = [0]
    def recorded_result(identity):
      calls[0] += 1
      return terminal(identity)
    out = retire_landed_attempt_ref(root=self.root, remote="origin",
      backend=self.backend, landed=landed,
      read_terminal=recorded_result, ref_kind="PRELIM")
    self.assertTrue(out.absent_after)
    self.assertEqual(calls[0], 2)
    self.assertIsNone(self.remote_sha(P))
    self.assertEqual(self.remote_sha(I), self.a)

  def test_forged_eligible_plan_does_not_bypass_live_proof(self):
    forged = replace(self.plan, landed_sha="f"*40)
    landed, read_terminal = self.evidence(self.plan)
    with self.assertRaisesRegex(PrelimRetirementError, "differs"):
      retire_verified_ref(self.root, "origin", forged, P, self.a,
        backend=self.backend, landed=landed, read_terminal=read_terminal)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_prelim_deletion_denies_wrong_expected_sha(self):
    landed, read_terminal = self.evidence(self.plan)
    with self.assertRaisesRegex(PrelimRetirementError, "ref SHA"):
      retire_verified_ref(self.root, "origin", self.plan, P, self.b,
        backend=self.backend, landed=landed, read_terminal=read_terminal)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_int_attempt_deletion_denies_wrong_expected_sha(self):
    landed, read_terminal = self.evidence(self.plan)
    with self.assertRaisesRegex(PrelimRetirementError, "ref SHA"):
      retire_verified_ref(self.root, "origin", self.plan, I, self.b,
        backend=self.backend, landed=landed, read_terminal=read_terminal)
    self.assertEqual(self.remote_sha(I), self.a)

  def test_no_independent_terminal_readback_refuses_deletion(self):
    landed, _ = self.evidence(self.plan)
    with self.assertRaisesRegex(PrelimRetirementError, "terminal evidence"):
      retire_verified_ref(self.root, "origin", self.plan, P, self.a,
        backend=self.backend, landed=landed, read_terminal=lambda _: None)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_unavailable_provider_push_is_unknown_not_success(self):
    original = subprocess.run
    def lose_push(args, **kwargs):
      if "push" in args:
        raise subprocess.TimeoutExpired(args, 30)
      return original(args, **kwargs)
    from unittest.mock import patch
    with patch("repo_workflow.prelim_retirement_remote.subprocess.run",
               side_effect=lose_push):
      with self.assertRaisesRegex(PrelimRetirementError, "UNKNOWN"):
        self.retire(self.plan, P, self.a)
    self.assertEqual(self.remote_sha(P), self.a)

  def test_competing_writer_at_push_cannot_delete_ref(self):
    original = subprocess.run
    raced = [False]
    def move_ref(args, **kwargs):
      if not raced[0] and "push" in args:
        raced[0] = True
        original(["git", "-C", str(self.root), "push", "--force",
                  "origin", self.b + ":" + P],
                 check=True, capture_output=True, text=True)
      return original(args, **kwargs)
    from unittest.mock import patch
    with patch("repo_workflow.prelim_retirement_remote.subprocess.run",
               side_effect=move_ref):
      with self.assertRaisesRegex(PrelimRetirementError, "UNKNOWN"):
        self.retire(self.plan, P, self.a)
    self.assertTrue(raced[0])
    self.assertEqual(self.remote_sha(P), self.b)

  def test_missing_authenticated_backend_is_rejected(self):
    with self.assertRaisesRegex(PrelimRetirementError, "repository"):
      landed, read_terminal = self.evidence(self.plan)
      retire_verified_ref(self.root, "origin", self.plan, P, self.a,
        backend=None, landed=landed, read_terminal=read_terminal)
    self.assertEqual(self.remote_sha(P), self.a)


if __name__ == "__main__":
  unittest.main()
