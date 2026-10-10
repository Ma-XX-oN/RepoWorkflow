"""Durable validation evidence acceptance and tamper tests (#69)."""

import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.state_store import WriterIdentity
from repo_workflow.validation_store import (
  ValidationEvidenceStore, ValidationObservation, ValidationStoreError,
)


SHA = "a" * 40
FINGERPRINT = "b" * 64


def observation(record_id="run-001", **overrides):
  fields = dict(
    record_id=record_id, candidate_sha=SHA, version="0.1.7",
    branch="issue-69", unit="ART/a", fingerprint=FINGERPRINT,
    verdict="PASS", mode="automated", runner="python-3.13",
    platform="linux-x86_64", provider_run="local/run/1",
  )
  fields.update(overrides)
  return ValidationObservation(**fields)


class DurableEvidenceAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    self.store = ValidationEvidenceStore(self.root)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_initially_empty_and_create_read(self):
    self.assertEqual(self.store.list_ids(), ())
    item = observation()
    record = self.store.publish(item, self.writer)
    self.assertEqual(record["revision"], 0)
    self.assertEqual(record["writer_id"], "agent-a")
    self.assertEqual(record["session_id"], "session-1")
    self.assertEqual(self.store.read(item.record_id), item)
    self.assertEqual(self.store.list_ids(), (item.record_id,))

  def test_restart_reconstructs_exact_evidence(self):
    item = observation()
    self.store.publish(item, self.writer)
    restarted = ValidationEvidenceStore(self.root)
    self.assertEqual(restarted.read(item.record_id), item)
    self.assertEqual(restarted.list_ids(), ("run-001",))

  def test_duplicate_id_never_replaces_record(self):
    old = observation()
    self.store.publish(old, self.writer)
    with self.assertRaises(ValidationStoreError):
      self.store.publish(observation(verdict="FAIL"), self.writer)
    self.assertEqual(self.store.read("run-001"), old)

  def test_distinct_observations_do_not_conflict(self):
    self.store.publish(observation("run-001"), self.writer)
    second = observation("run-002", candidate_sha="c" * 40,
                         provider_run="github/2", platform="windows-amd64")
    self.store.publish(second, WriterIdentity("agent-b", "session-2"))
    self.assertEqual(self.store.list_ids(), ("run-001", "run-002"))
    self.assertEqual(self.store.read("run-002"), second)

  def test_tampered_payload_detected(self):
    self.store.publish(observation(), self.writer)
    path = self.root / ".repoworkflow" / "validation" / "records" / "run-001.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["value"]["payload"]["verdict"] = "FAIL"
    path.write_text(json.dumps(record), encoding="utf-8")
    with self.assertRaisesRegex(ValidationStoreError, "digest mismatch"):
      self.store.read("run-001")

  def test_corrupt_durable_envelope_fails_closed(self):
    self.store.publish(observation(), self.writer)
    path = self.root / ".repoworkflow" / "validation" / "records" / "run-001.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["schema_version"] = 9
    path.write_text(json.dumps(record), encoding="utf-8")
    with self.assertRaises(ValidationStoreError):
      self.store.read("run-001")

  def test_strict_field_set_and_digest(self):
    item = observation()
    self.store.publish(item, self.writer)
    path = self.root / ".repoworkflow" / "validation" / "records" / "run-001.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["value"]["payload"]["unrecognized"] = "data"
    path.write_text(json.dumps(record), encoding="utf-8")
    with self.assertRaises(ValidationStoreError):
      self.store.read("run-001")

  def test_missing_record_fails_closed(self):
    with self.assertRaises(ValidationStoreError):
      self.store.read("run-001")

  def test_invalid_identity_rejected_before_write(self):
    for invalid in ("", "../traversal", "UPPER", "bad/id", "white space"):
      with self.subTest(invalid=invalid):
        with self.assertRaises(ValidationStoreError):
          observation(invalid)
    self.assertEqual(self.store.list_ids(), ())

  def test_invalid_candidate_provenance_or_result_rejected(self):
    for field, value in (
      ("candidate_sha", "abcd"), ("version", ""), ("branch", " bad"),
      ("fingerprint", "bad"), ("verdict", "SUCCESS"),
      ("mode", "unknown"), ("platform", ""), ("runner", " "),
      ("provider_run", ""),
    ):
      with self.subTest(field=field):
        with self.assertRaises(ValidationStoreError):
          observation(**{field: value})

  def test_reader_fails_closed_on_unexpected_file(self):
    folder = self.store.records.root / "records"
    folder.mkdir(parents=True)
    (folder / "unrecognized.txt").write_text("unexpected", encoding="utf-8")
    with self.assertRaises(ValidationStoreError):
      self.store.list_ids()

  def test_coverage_adapter_preserves_verdict_and_identity(self):
    item = observation(mode="manual", unit="MIT/manual")
    self.store.publish(item, self.writer)
    evidence = self.store.read("run-001").coverage()
    self.assertEqual(evidence.unit, "MIT/manual")
    self.assertEqual(evidence.mode, "manual")
    self.assertEqual(evidence.verdict, "PASS")
    self.assertEqual(evidence.fingerprint, FINGERPRINT)


if __name__ == "__main__":
  unittest.main()
