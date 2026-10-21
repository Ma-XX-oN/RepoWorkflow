"""Canonical landed results never manufacture a PASS at merge SHA."""
from dataclasses import replace
import json
import unittest

from repo_workflow.done_evidence_promotion import (
  AuthenticatedStage, Promotion,
)
from repo_workflow.done_results_discovery import (
  LandedResultsError, discover_landed_results,
)

A,B,C=("a"*40,"b"*40,"c"*40)


class Provider:
  def __init__(self):
    self.tip={"destination":"main","sha":B,
              "independently_authenticated":True}
    self.promotion=Promotion(
      "integration-op-1",A,A,C,B,A,A,"context",tuple(
        AuthenticatedStage(
          kind,A,"hosted-"+kind,"artifact-"+kind,
          "catalogue","config","inputs","2027-01-01T00:00:00Z",
          "PASS",True)
        for kind in ("regression","integration","release")))
    self.source=json.dumps({
      "testSHA":A,"kind":"regression","result":"PASS",
      "runner":"hosted","groups":[]
    })+"\n"
    self.events=[]
    self.move_after=False

  def destination(self,dest):
    self.events.append("destination")
    if self.move_after and self.events.count("destination")>=2:
      return {**self.tip,"sha":C}
    return dict(self.tip)

  def relation(self,dest,sha):
    self.events.append("promotion")
    return self.promotion

  def logs(self,sha):
    self.events.append("source")
    return self.source

  def read(self,**override):
    args={
      "destination":"main","landed_sha":B,
      "read_destination":self.destination,
      "read_promotion":self.relation,
      "read_source_log":self.logs,
    }
    return discover_landed_results(**{**args,**override})


class LandedTests(unittest.TestCase):
  def setUp(self):
    self.p=Provider()

  def test_source_sha_preserved_and_landing_identified_separately(self):
    record=self.p.read()
    self.assertEqual(record.tested_source_sha,A)
    self.assertEqual(record.landed_sha,B)
    self.assertEqual(record.original_results[0]["testSHA"],A)
    self.assertNotEqual(record.original_results[0]["testSHA"],B)
    self.assertEqual(self.p.events,[
      "destination","promotion","source","destination","promotion"])

  def test_incomplete_or_forged_release_never_discovered(self):
    original=self.p.promotion
    for value in ((),original.stages[:2],tuple(replace(
        r,authenticated=False) if r.stage=="release" else r
        for r in original.stages),tuple(replace(
        r,source_sha=B) if r.stage=="integration" else r
        for r in original.stages)):
      self.p.promotion=replace(original,stages=value)
      with self.subTest(value=value):
        with self.assertRaisesRegex(LandedResultsError,"not authenticated"):
          self.p.read()
    self.p.promotion=original

  def test_destination_advanced_after_source_read_refused(self):
    self.p.move_after=True
    with self.assertRaisesRegex(LandedResultsError,"moved"):
      self.p.read()

  def test_foreign_or_old_promotion_refused(self):
    self.p.promotion=replace(self.p.promotion,landed_sha=C)
    with self.assertRaisesRegex(LandedResultsError,"not authenticated"):
      self.p.read()

  def test_foreign_source_log_refused(self):
    self.p.source=json.dumps({
      "testSHA":B,"kind":"regression","result":"PASS",
      "runner":"hosted"})+"\n"
    with self.assertRaisesRegex(LandedResultsError,"test SHA differs"):
      self.p.read()

  def test_noncanonical_log_never_inferred_pass(self):
    self.p.source='{"testSHA":"'+A+'","testSHA":"'+A+'"}'
    with self.assertRaisesRegex(LandedResultsError,"UNKNOWN"):
      self.p.read()

  def test_missing_provider_never_discovers_result(self):
    with self.assertRaisesRegex(LandedResultsError,"readers"):
      self.p.read(read_promotion=None)


if __name__=="__main__":
  unittest.main()
