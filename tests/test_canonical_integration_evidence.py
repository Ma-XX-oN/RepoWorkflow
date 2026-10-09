"""Specification tests for canonical integration pre-merge evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from repo_workflow.test_evidence_gate import (
  CanonicalEvidenceError, require_integration_evidence,
)


class CanonicalIntegrationEvidenceTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.path = Path(self.tmp.name) / "testResults-542.jsonl"
    self.sha = "a" * 40
    self.base = {
      "kind": "integration", "testSHA": self.sha,
      "platform": {"os": "Linux", "runtime": "3.13"},
      "runner": "local", "result": "succeeded",
      "reusable": True, "uncommittedChanges": [],
      "headChangedDuringTest": False,
    }

  def write(self, *records):
    self.path.write_text(
      "".join(json.dumps(record) + "\n" for record in records),
      encoding="utf-8",
    )

  def verify(self, *platforms):
    require_integration_evidence(
      self.path, candidate=self.sha, required_platforms=platforms or ("Linux",),
    )

  def test_empty_required_platforms_cannot_vacuously_pass(self):
    self.write(self.base)
    with self.assertRaisesRegex(
      CanonicalEvidenceError, "platforms unspecified",
    ):
      require_integration_evidence(
        self.path, candidate=self.sha, required_platforms=(),
      )

  def test_exact_clean_local_pass(self):
    self.write(self.base)
    self.verify()

  def test_missing_malformed_and_other_candidate_fail(self):
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()
    self.path.write_text("{")
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()
    self.write({**self.base, "testSHA": "b" * 40})
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()

  def test_later_failure_invalidates_earlier_pass(self):
    self.write(self.base, {**self.base, "result": "failed"})
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()
    self.write(self.base, {**self.base, "result": "failed"}, self.base)
    self.verify()

  def test_dirty_and_nonreusable_cannot_satisfy_gate(self):
    for bad in (
      {"uncommittedChanges": ["file.py"]},
      {"headChangedDuringTest": True},
      {"reusable": False},
      {"result": "incomplete"},
      {"result": "SKIPPED"},
    ):
      with self.subTest(bad=bad):
        self.write({**self.base, **bad})
        with self.assertRaises(CanonicalEvidenceError):
          self.verify()

  def test_required_environment_matrix_is_complete(self):
    windows = {**self.base, "platform": {"os": "Windows"}}
    self.write(self.base, windows)
    self.verify("Linux", "Windows")
    with self.assertRaises(CanonicalEvidenceError):
      self.verify("Linux", "Windows", "Darwin")

  def test_hosted_record_requires_consistent_provider_identity(self):
    hosted = {
      **self.base, "runner": "github-actions",
      "providerRunId": 123, "providerCandidateSHA": self.sha,
      "providerInvocationSHA": "b" * 40,
      "providerStage": "integration-testing",
    }
    self.write(hosted)
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()
    require_integration_evidence(
      self.path, candidate=self.sha, required_platforms=("Linux",),
      verify_hosted=lambda record: record["providerRunId"] == 123,
    )
    with self.assertRaises(CanonicalEvidenceError):
      require_integration_evidence(
        self.path, candidate=self.sha, required_platforms=("Linux",),
        verify_hosted=lambda record: False,
      )
    for changed in (
      {"providerRunId": None},
      {"providerRunId": True},
      {"providerCandidateSHA": "b" * 40},
      {"providerInvocationSHA": "invalid"},
      {"providerStage": "regression-testing"},
    ):
      with self.subTest(changed=changed):
        self.write({**hosted, **changed})
        with self.assertRaises(CanonicalEvidenceError):
          self.verify()

  def test_regression_pass_does_not_replace_integration(self):
    self.write({**self.base, "kind": "regression"})
    with self.assertRaises(CanonicalEvidenceError):
      self.verify()


if __name__ == "__main__":
  unittest.main()
