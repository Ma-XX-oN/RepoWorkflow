"""Independent negative contracts for exact source-to-landed promotion."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from repo_workflow.done_evidence_promotion import (
  AuthenticatedStage, PromotionError, make_promotion, publish_promotion,
)


A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40


class PromotionTests(unittest.TestCase):
  def setUp(self):
    self.stages = tuple(AuthenticatedStage(
      stage, A, f"run-{stage}", f"artifact-{stage}",
      "catalogue-hash", "config-hash", "inputs-hash",
      "2027-01-01T00:00:00Z", "PASS", True)
      for stage in ("regression", "integration", "release"))
    self.inputs = {
      "operation_id": "integrate-123",
      "tested_source_sha": A,
      "accepted_candidate_sha": B,
      "target_before_sha": C,
      "landed_sha": D,
      "landed_tree_sha": A,
      "source_tree_sha": A,
      "context_digest": "context-sha256",
      "stages": self.stages,
      "independently_verified_landing": True,
      "equivalent_test_inputs": True,
      "as_of_utc": datetime(2026,10,20,tzinfo=timezone.utc),
    }

  def make(self, **changes):
    return make_promotion(**{**self.inputs, **changes})

  def test_exact_success_retains_true_test_source(self):
    record = self.make()
    self.assertEqual(record.tested_source_sha, A)
    self.assertEqual(record.landed_sha, D)
    self.assertEqual(record.disposition,
                     "source-tested-accepted-at-destination")

  def test_no_hosted_release_stage_cannot_be_inferred(self):
    with self.assertRaisesRegex(PromotionError, "complete independent"):
      self.make(stages=self.stages[:2])

  def test_forged_pass_rejected(self):
    for changes in (
      {"authenticated": False},
      {"status": "FAIL"},
      {"status": "INCOMPLETE"},
      {"source_sha": B},
      {"artifact_digest": ""},
    ):
      with self.subTest(changes=changes):
        altered = replace(self.stages[0], **changes)
        with self.assertRaises(PromotionError):
          self.make(stages=(altered, *self.stages[1:]))

  def test_changed_tree_or_context_rejected(self):
    for changes in (
      {"landed_tree_sha": B},
      {"independently_verified_landing": False},
      {"equivalent_test_inputs": False},
      {"context_digest": ""},
    ):
      with self.subTest(changes=changes):
        with self.assertRaises(PromotionError):
          self.make(**changes)

  def test_expired_or_malformed_evidence_is_denied(self):
    for expiry in ("2026-10-19T00:00:00Z", "not-a-date",
                   "2026-10-20T00:00:00Z"):
      bad=replace(self.stages[0], expires_at=expiry)
      with self.subTest(expiry=expiry):
        with self.assertRaises(PromotionError):
          self.make(stages=(bad,self.stages[1],self.stages[2]))

  def test_untrusted_clock_is_rejected(self):
    with self.assertRaisesRegex(PromotionError,"UTC evaluation"):
      self.make(as_of_utc=datetime(2026,10,20))

  def test_mixed_catalogue_and_config_denied(self):
    bad=replace(self.stages[1], catalogue_digest="other-catalogue")
    with self.assertRaisesRegex(PromotionError,"inconsistent"):
      self.make(stages=(self.stages[0],bad,self.stages[2]))

  def test_lost_publication_ack_reconciled_only_by_exact_record(self):
    record=self.make()
    saved={}
    calls=[]
    def persist(value):
      calls.append(value.operation_id)
      saved[value.operation_id] = value
      raise TimeoutError("lost ACK after durable append")
    result=publish_promotion(record,persist=persist,
                             readback=lambda op:saved.get(op))
    self.assertEqual(result,record)
    self.assertEqual(calls,["integrate-123"])

  def test_absent_or_foreign_provider_record_rejected(self):
    record=self.make()
    for response in (None, replace(record,landed_sha=B), True):
      with self.subTest(response=response):
        with self.assertRaisesRegex(PromotionError,"not persisted"):
          publish_promotion(record,persist=lambda r:None,
                            readback=lambda op:response)

  def test_unknown_readback_fails_closed(self):
    record=self.make()
    def fail(op):
      raise ConnectionError("down")
    with self.assertRaisesRegex(PromotionError,"UNKNOWN"):
      publish_promotion(record,persist=lambda r:None,readback=fail)


if __name__ == "__main__":
  unittest.main()
