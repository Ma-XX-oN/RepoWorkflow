"""State transitions and contradictory provider observations for issue #110."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.state_store import WriterIdentity
from repo_workflow.validation_coverage import Requirement
from repo_workflow.validation_plan import (
  ValidationPlanError, dispatch_missing, plan_from_store,
)
from repo_workflow.validation_store import ValidationEvidenceStore, ValidationObservation


A = "a" * 40
B = "b" * 40
FP = "c" * 64


def request():
  return {
    "contract_version": 1, "operation": "execute",
    "invocation_id": "provider-status",
    "candidate": {"repository": "owner/repo", "commit": A, "base": B},
    "requirements": {"stages": [], "capabilities": [], "artifacts": []},
    "inputs": {"base": B},
  }


class ProviderConsistencyTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    self.store = ValidationEvidenceStore(self.root)
    self.required = [Requirement("unit/a", FP)]

  def plan(self, sha=A, fingerprint=FP, trust=frozenset({"local"})):
    return plan_from_store(
      self.store, [Requirement("unit/a", fingerprint)], sha,
      trusted_record_ids=trust, equivalent_candidate_shas=frozenset(),
    )

  def test_lifecycle_before_and_after_immutable_observation(self):
    before = self.plan()
    self.assertEqual(before.automated_units, ("unit/a",))
    record = ValidationObservation(
      record_id="local", candidate_sha=A, version="0.1.1",
      branch="issue-110", unit="unit/a", fingerprint=FP,
      verdict="PASS", mode="automated", runner="python",
      platform="linux", provider_run="local/1",
    )
    self.store.publish(record, WriterIdentity("writer", "session"))
    after = self.plan()
    self.assertEqual(after.automated_units, ())
    self.assertTrue(after.complete)
    restarted_store = ValidationEvidenceStore(self.root)
    restarted = plan_from_store(
      restarted_store, self.required, A,
      trusted_record_ids=frozenset({"local"}),
      equivalent_candidate_shas=frozenset(),
    )
    self.assertEqual(restarted, after)
    self.assertEqual(self.plan(sha=B).automated_units, ("unit/a",))
    self.assertEqual(self.plan(fingerprint="d" * 64).automated_units,
                     ("unit/a",))
    self.assertEqual(self.plan(trust=frozenset()).automated_units,
                     ("unit/a",))

  def test_provider_status_must_match_actual_exit_code(self):
    plan = self.plan(trust=frozenset())
    for outcome, exit_code in (
      ("succeeded", 15),
      ("failed", 0),
      ("succeeded", True),
      ("failed", None),
    ):
      with self.subTest(outcome=outcome, code=exit_code):
        reply = {
          "status": "ok",
          "candidate": request()["candidate"],
          "observations": {"stages": [{
            "stage": "unit/a", "candidate": request()["candidate"],
            "complete": True, "outcome": outcome,
            "exit_code": exit_code,
          }]},
        }
        with patch("repo_workflow.validation_plan.dispatch", return_value=reply):
          with self.assertRaises(ValidationPlanError):
            dispatch_missing(
              self.root, plan, request(), {"unit/a": "registered-group"},
            )


if __name__ == "__main__":
  unittest.main()
