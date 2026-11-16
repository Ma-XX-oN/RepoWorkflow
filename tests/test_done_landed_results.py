"""Projection and canonical readback preserve original tested source SHA."""
from dataclasses import replace
import unittest

from repo_workflow.done_landed_results import (
  canonical_landed_result, read_landed_results,
)
from repo_workflow.done_evidence_promotion import PromotionError
from tests.test_done_evidence_promotion import PromotionTests, A, B, C, D


class LandedResultsTests(unittest.TestCase):
  def setUp(self):
    self.evidence=PromotionTests()
    self.evidence.setUp()
    self.record=self.evidence.make()

  def test_canonical_record_preserves_provenance_not_landed_pass(self):
    raw=canonical_landed_result(self.record)
    self.assertEqual(raw["testSHA"],A)
    self.assertEqual(raw["landedSHA"],D)
    self.assertEqual(raw["result"],"promoted")
    self.assertNotEqual(raw["runner"],"github-actions")
    self.assertEqual(len(raw["sourceStages"]),3)

  def test_read_canonical_landed_tip_from_provider(self):
    result=read_landed_results(
      landed_sha=D,read_promotion=lambda sha:(self.record,))
    self.assertEqual(result[0]["testSHA"],A)
    self.assertEqual(result[0]["landedSHA"],D)

  def test_forged_foreign_sha_cannot_be_returned(self):
    with self.assertRaisesRegex(PromotionError,"foreign"):
      read_landed_results(
        landed_sha=B,read_promotion=lambda sha:(self.record,))

  def test_duplicate_promotion_operation_refused(self):
    with self.assertRaisesRegex(PromotionError,"duplicate"):
      read_landed_results(
        landed_sha=D,read_promotion=lambda sha:(self.record,self.record))

  def test_provider_missing_reader_denied(self):
    with self.assertRaisesRegex(PromotionError,"reader required"):
      read_landed_results(landed_sha=D,read_promotion=None)

  def test_unknown_provider_response_not_empty_success(self):
    def unavailable(sha):
      raise TimeoutError("not available")
    with self.assertRaisesRegex(PromotionError,"UNKNOWN"):
      read_landed_results(landed_sha=D,read_promotion=unavailable)

  def test_untyped_local_log_rejected(self):
    with self.assertRaisesRegex(PromotionError,"promotions invalid"):
      read_landed_results(landed_sha=D,read_promotion=lambda sha:[])


if __name__=="__main__":
  unittest.main()
