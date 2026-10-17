"""GitHub API ref/ancestry proof for #103 retirement."""
import unittest

from repo_workflow.prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from repo_workflow.prelim_retirement_github import verify_github_retirement

S="a"*40
A="b"*40
L="c"*40
T="d"*40
P="refs/heads/PRELIM-issue-123/main-11111111-1111-4111-8111-111111111111"
I="refs/heads/INT-ATTEMPT-issue-123/main-22222222-2222-4222-8222-222222222222"
D="refs/heads/main"


class Missing(Exception):
  code="not_found"


class Backend:
  def __init__(self):
    self.refs={P:S,D:T}
    self.calls=[]
    self.status="ahead"
    self.head=T
    self.base=L
    self.behind=0

  def get(self, path):
    self.calls.append(path)
    if path.startswith("git/ref/"):
      ref="refs/"+path.removeprefix("git/ref/")
      if ref not in self.refs:
        raise Missing()
      return {"ref":ref,"object":{"sha":self.refs[ref]}}
    if path.startswith("compare/"):
      return {"base_commit":{"sha":self.base},
              "head_commit":{"sha":self.head},
              "status":self.status,"behind_by":self.behind}
    raise AssertionError("unexpected provider operation")


class GithubRetirementTests(unittest.TestCase):
  def setUp(self):
    self.backend=Backend()
    self.landed=LandedIntegration(P,S,I,A,D,L,"op-123","terminal-123")
    self.terminal={
      "status":"integrated","prelim_ref":P,"prelim_sha":S,
      "int_attempt_ref":I,"accepted_sha":A,
      "destination_ref":D,"landed_sha":L,
      "integration_id":"op-123","terminal_evidence_ref":"terminal-123",
    }

  def verify(self):
    return verify_github_retirement(self.backend,self.landed,
      lambda identity:self.terminal)

  def test_verified_exact_provider_comparison(self):
    self.assertTrue(self.verify().eligible_for_ref_retirement)
    self.assertIn("compare/"+L+"..."+T,self.backend.calls)

  def test_old_landed_commit_not_ancestor(self):
    self.backend.status="diverged"
    with self.assertRaises(PrelimRetirementError):
      self.verify()

  def test_forged_head_rejected(self):
    self.backend.head=S
    with self.assertRaises(PrelimRetirementError):
      self.verify()

  def test_forged_base_rejected(self):
    self.backend.base=A
    with self.assertRaises(PrelimRetirementError):
      self.verify()

  def test_missing_landed_ref_requires_terminal_readback(self):
    self.backend.refs.pop(P)
    self.assertTrue(self.verify().eligible_for_ref_retirement)
    self.terminal=None
    with self.assertRaises(PrelimRetirementError):
      self.verify()

  def test_branch_moved_rejected(self):
    self.backend.refs[P]="e"*40
    with self.assertRaises(PrelimRetirementError):
      self.verify()

  def test_ancestry_unknown_denied(self):
    self.backend.behind=1
    with self.assertRaises(PrelimRetirementError):
      self.verify()


if __name__=="__main__":
  unittest.main()
