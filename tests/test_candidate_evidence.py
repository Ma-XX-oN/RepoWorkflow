"""Contract tests for durable #69/#95 candidate eligibility handoff."""
import unittest
from dataclasses import dataclass, replace
from types import SimpleNamespace
from repo_workflow.candidate_evidence import EvidenceGateError, read_evidence_gate


@dataclass(frozen=True)
class Requirement:
  unit: str
  fingerprint: str
  mode: str = "automated"


@dataclass(frozen=True)
class Observation:
  record_id: str
  candidate_sha: str
  version: str
  branch: str
  unit: str
  fingerprint: str
  verdict: str
  mode: str = "automated"

  def coverage(self):
    return self


class Store:
  def __init__(self, records):
    self.records = {record.record_id: record for record in records}

  def read(self, record_id):
    return self.records[record_id]


def evaluate(requirements, evidence):
  statuses = []
  for requirement in sorted(requirements, key=lambda item: item.unit):
    relevant = [
      obs for obs in evidence
      if obs.unit == requirement.unit
      and obs.fingerprint == requirement.fingerprint
      and (requirement.mode != "manual" or obs.mode == "manual")
    ]
    state = "satisfied" if any(e.verdict == "PASS" for e in relevant) else "missing"
    statuses.append((requirement.unit, state))
  return SimpleNamespace(statuses=tuple(statuses))


class EvidenceHandoffTests(unittest.TestCase):
  def setUp(self):
    self.candidate = "a" * 40
    self.records = [
      Observation("one", self.candidate, "v1", "feature", "unit-a", "b" * 64, "PASS"),
      Observation("two", self.candidate, "v1", "feature", "unit-b", "c" * 64, "PASS"),
    ]
    self.required = [Requirement("unit-a", "b" * 64), Requirement("unit-b", "c" * 64)]

  def check(self, records=None, required=None, ids=None, candidate=None):
    return read_evidence_gate(
      Store(self.records if records is None else records),
      self.required if required is None else required,
      ["one", "two"] if ids is None else ids,
      candidate=self.candidate if candidate is None else candidate,
      version="v1", branch="feature", coverage_evaluator=evaluate,
    )

  def test_two_verified_pass_units_complete(self):
    result = self.check()
    self.assertEqual(result.tested, self.candidate)
    self.assertTrue(all((
      result.complete, result.passed, result.inputs_current,
      result.required_checks_complete, result.applicable, result.authenticated,
    )))

  def test_failed_stale_and_changed_inputs_never_pass(self):
    for field, value in (
      ("verdict", "FAIL"),
      ("fingerprint", "d" * 64),
      ("mode", "manual"),
    ):
      with self.subTest(field=field):
        records = [self.records[0], replace(self.records[1], **{field: value})]
        required = self.required
        if field == "mode":
          required = [self.required[0], Requirement("unit-b", "c" * 64, "manual")]
          records = [self.records[0], replace(self.records[1], mode="automated")]
        self.assertFalse(self.check(records=records, required=required).passed)
    for field, value in (
      ("candidate_sha", "d" * 40),
      ("branch", "other"),
      ("version", "other"),
      ("record_id", "forged"),
    ):
      with self.subTest(field=field):
        records = [replace(self.records[0], **{field: value}), self.records[1]]
        with self.assertRaises(EvidenceGateError):
          self.check(records=records)

  def test_missing_duplicate_and_broken_records_denied(self):
    for ids, required in (
      ([], self.required),
      (["one", "one"], self.required),
      (["missing"], self.required),
      (["one"], []),
      (["one", "two"], [self.required[0], self.required[0]]),
    ):
      with self.subTest(ids=ids, required=required):
        with self.assertRaises(EvidenceGateError):
          self.check(ids=ids, required=required)

  def test_manifest_requires_all_units(self):
    self.assertFalse(self.check(ids=["one"]).passed)


if __name__ == "__main__":
  unittest.main()
