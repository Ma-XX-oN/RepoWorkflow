"""Retirement orchestration must recheck independent provider proof."""
from unittest.mock import patch
import unittest

from repo_workflow.prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from repo_workflow.prelim_retirement_execute import retire_landed_attempt_ref

P="refs/heads/PRELIM-issue-123/main-11111111-1111-4111-8111-111111111111"
I="refs/heads/INT-ATTEMPT-issue-123/main-11111111-1111-4111-8111-111111111111"
D="refs/heads/main"
S="a"*40
A="b"*40
L="c"*40
T="d"*40


class Backend:
  def __init__(self):
    self.refs={P:S,I:A,D:T}
    self.status="ahead"

  def get(self, route):
    if route.startswith("git/ref/"):
      ref="refs/"+route.removeprefix("git/ref/")
      return {"ref":ref,"object":{"sha":self.refs[ref]}}
    if route == "compare/"+A+"..."+L:
      return {
        "base_commit":{"sha":A},
        "merge_base_commit":{"sha":A},
        "status":"ahead",
        "behind_by":0,
      }
    if route == "compare/"+L+"..."+T:
      return {
        "base_commit":{"sha":L},
        "merge_base_commit":{"sha":L},
        "status":self.status,
        "behind_by":0,
      }
    raise AssertionError(route)


class RetirementExecuteTests(unittest.TestCase):
  def setUp(self):
    self.backend=Backend()
    self.landed=LandedIntegration(P,S,I,A,D,L,"op-1","terminal-1")
    self.terminal={
      "status":"integrated","prelim_ref":P,"prelim_sha":S,
      "int_attempt_ref":I,"accepted_sha":A,"destination_ref":D,
      "landed_sha":L,"integration_id":"op-1",
      "terminal_evidence_ref":"terminal-1",
    }

  def run_case(self, kind="PRELIM"):
    return retire_landed_attempt_ref(
      root=".",remote="origin",backend=self.backend,
      landed=self.landed,read_terminal=lambda ref:self.terminal,
      ref_kind=kind)

  def test_prelim_delete_uses_verified_prelim_sha(self):
    with patch("repo_workflow.prelim_retirement_execute.retire_verified_ref") as do:
      self.run_case()
    args=do.call_args.args
    self.assertEqual((args[3],args[4]),(P,S))
    self.assertIs(do.call_args.kwargs["backend"],self.backend)

  def test_int_attempt_delete_uses_exact_accepted_sha(self):
    with patch("repo_workflow.prelim_retirement_execute.retire_verified_ref") as do:
      self.run_case(kind="INT-ATTEMPT")
    args=do.call_args.args
    self.assertEqual((args[3],args[4]),(I,A))
    self.assertIs(do.call_args.kwargs["backend"],self.backend)

  def test_missing_terminal_prevents_any_delete(self):
    self.terminal=None
    with patch("repo_workflow.prelim_retirement_execute.retire_verified_ref") as do:
      with self.assertRaises(PrelimRetirementError):
        self.run_case()
    do.assert_not_called()

  def test_unproven_landing_prevents_any_delete(self):
    self.backend.status="diverged"
    with patch("repo_workflow.prelim_retirement_execute.retire_verified_ref") as do:
      with self.assertRaises(PrelimRetirementError):
        self.run_case()
    do.assert_not_called()

  def test_unrelated_ref_kind_rejected(self):
    with patch("repo_workflow.prelim_retirement_execute.retire_verified_ref") as do:
      with self.assertRaises(PrelimRetirementError):
        self.run_case(kind="main")
    do.assert_not_called()


if __name__=="__main__":
  unittest.main()
