"""Black-box imported evidence acceptance criteria (#70)."""

import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.state_store import WriterIdentity
from repo_workflow.validation_coverage import Requirement
from repo_workflow.validation_import import classify_import, import_from_store
from repo_workflow.validation_store import (
  ValidationEvidenceStore, ValidationObservation, ValidationStoreError,
)


A = "a" * 40
B = "b" * 40
F = "c" * 64
G = "d" * 64


def obs(record_id="local-one", **overrides):
  values = dict(
    record_id=record_id, candidate_sha=A, version="0.1.7",
    branch="issue-70", unit="ART/a", fingerprint=F,
    verdict="PASS", mode="automated", runner="python-3.13",
    platform="linux-x86_64", provider_run="local/123",
  )
  values.update(overrides)
  return ValidationObservation(**values)


def classify(required=None, observations=None, target=A,
             trust=frozenset({"local-one"}),
             equivalents=frozenset()):
  return classify_import(
    [Requirement("ART/a", F)] if required is None else required,
    [obs()] if observations is None else observations, target,
    trusted_record_ids=trust,
    equivalent_candidate_shas=equivalents,
  )


class ImportAcceptance(unittest.TestCase):
  def test_exact_candidate_and_inputs_are_applicable(self):
    decision = classify()[0]
    self.assertEqual(decision.status, "applicable")
    self.assertEqual(decision.accepted_record_ids, ("local-one",))

  def test_missing_unit_is_missing(self):
    decision = classify(observations=[])[0]
    self.assertEqual(decision.status, "missing")

  def test_different_candidate_requires_explicit_equivalence_proof(self):
    self.assertEqual(classify(target=B)[0].status, "stale")
    self.assertEqual(classify(target=B, equivalents=frozenset({A}))[0].status,
                     "applicable")

  def test_changed_inputs_invalidate_even_with_equivalence_proof(self):
    decision = classify(required=[Requirement("ART/a", G)],
                        target=B, equivalents=frozenset({A}))[0]
    self.assertEqual(decision.status, "stale")

  def test_untrusted_provenance_is_never_imported(self):
    decision = classify(trust=frozenset())[0]
    self.assertEqual(decision.status, "unusable")
    self.assertIn("untrusted provenance", decision.reason)

  def test_nonpass_cannot_be_imported(self):
    for verdict in ("FAIL", "INCOMPLETE", "PENDING"):
      with self.subTest(verdict=verdict):
        decision = classify(observations=[obs(verdict=verdict)])[0]
        self.assertEqual(decision.status, "unusable")

  def test_manual_requirement_never_uses_automated_evidence(self):
    manual = [Requirement("ART/a", F, "manual")]
    decision = classify(required=manual)[0]
    self.assertEqual(decision.status, "unusable")
    self.assertEqual(classify(required=manual,
                              observations=[obs(mode="manual")])[0].status,
                     "applicable")

  def test_no_evidence_semantic_mutation(self):
    original = obs()
    classify(observations=[original])
    self.assertEqual(original.verdict, "PASS")
    self.assertEqual(original.candidate_sha, A)

  def test_multiple_records_deterministic_and_no_command_inference(self):
    records = [obs("local-one"), obs("hosted-two", provider_run="hosted/2")]
    decisions = classify(observations=records,
                         trust=frozenset({"local-one", "hosted-two"}))
    self.assertEqual(decisions[0].accepted_record_ids,
                     ("hosted-two", "local-one"))
    reordered = classify(observations=list(reversed(records)),
                         trust=frozenset({"local-one", "hosted-two"}))
    self.assertEqual(decisions, reordered)

  def test_missing_trust_or_equivalence_sets_fail_closed(self):
    with self.assertRaises(ValueError):
      classify(trust=None)
    with self.assertRaises(ValueError):
      classify(equivalents=None)

  def test_duplicate_requirement_fails_closed(self):
    with self.assertRaises(ValueError):
      classify(required=[Requirement("ART/a", F), Requirement("ART/a", F)])

  def test_malformed_target_sha_fails_closed(self):
    with self.assertRaises(ValueError):
      classify(target="not-a-git-sha")


class DurableImportTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    self.store = ValidationEvidenceStore(self.root)
    self.writer = WriterIdentity("agent", "session")

  def tearDown(self):
    self.temp.cleanup()

  def test_import_reads_durable_record_without_mutation(self):
    original = obs()
    self.store.publish(original, self.writer)
    decision = import_from_store(
      self.store, [Requirement("ART/a", F)], A,
      trusted_record_ids=frozenset({"local-one"}),
      equivalent_candidate_shas=frozenset(),
    )
    self.assertEqual(decision[0].status, "applicable")
    self.assertEqual(self.store.read("local-one"), original)

  def test_corrupted_durable_evidence_aborts_import(self):
    self.store.publish(obs(), self.writer)
    path = (self.root / ".repoworkflow" / "validation"
            / "records" / "local-one.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["value"]["payload"]["verdict"] = "FAIL"
    path.write_text(json.dumps(data), encoding="utf-8")
    with self.assertRaises(ValidationStoreError):
      import_from_store(
        self.store, [Requirement("ART/a", F)], A,
        trusted_record_ids=frozenset({"local-one"}),
        equivalent_candidate_shas=frozenset(),
      )


if __name__ == "__main__":
  unittest.main()
