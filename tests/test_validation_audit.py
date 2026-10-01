from pathlib import Path
import tempfile
import unittest

from repo_workflow.validation_audit import (
  ValidationAuditError,
  ValidationRecord,
  append_record,
  audit_path,
  latest_result_for_sha,
  read_records,
  records_for_sha,
  regression_reuse_decision,
)


SHA1 = "1" * 40
SHA2 = "2" * 40


def record(
  *,
  sha: str = SHA1,
  kind: str = "regression",
  result: str = "succeeded",
  branch: str = "issue-16-validation-audit",
  tag: str | None = "v1.2.3-issue.16.0.1",
) -> ValidationRecord:
  return ValidationRecord(
    timestamp="2026-10-01T22:00:00Z",
    kind=kind,
    baseVersion="1.2.3",
    branch=branch,
    testVersion="1.2.3-issue.16.0.1",
    testSHA=sha,
    candidateTag=tag,
    result=result,
    runner="local",
  )


class ValidationAuditTests(unittest.TestCase):
  def test_append_uses_per_issue_jsonl_and_preserves_order(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      first = record(result="incomplete", tag=None)
      second = record(result="succeeded")

      path = append_record(root, first)
      append_record(root, second)

      self.assertEqual(path, audit_path(root, 16))
      self.assertEqual(read_records(path), [first, second])
      self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

  def test_branch_remains_semantic_metadata_after_branch_deletion(self):
    original = record(branch="issue-16-now-deleted")
    parsed = ValidationRecord.from_json(original.to_json())
    self.assertEqual(parsed.branch, "issue-16-now-deleted")

  def test_exact_sha_reuse_never_transfers_to_changed_candidate(self):
    records = [record(sha=SHA1, result="succeeded")]
    self.assertEqual(regression_reuse_decision(records, SHA1), "reuse-pass")
    self.assertEqual(regression_reuse_decision(records, SHA2), "run")
    self.assertEqual(records_for_sha(records, SHA2), [])

  def test_missing_evidence_requires_validation(self):
    self.assertEqual(regression_reuse_decision([], SHA1), "run")

  def test_failed_and_incomplete_are_terminal_evidence_not_pass_reuse(self):
    for result in ("failed", "incomplete"):
      with self.subTest(result=result):
        self.assertEqual(
          regression_reuse_decision([record(result=result)], SHA1),
          "reuse-terminal",
        )

  def test_latest_same_sha_record_controls_kind_result(self):
    records = [
      record(kind="integration", result="failed"),
      record(kind="integration", result="succeeded"),
    ]
    self.assertEqual(
      latest_result_for_sha(records, SHA1, kind="integration"),
      "succeeded",
    )

  def test_different_issues_use_different_files(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      sixteen = record()
      seventeen = ValidationRecord(
        timestamp=sixteen.timestamp,
        kind=sixteen.kind,
        baseVersion=sixteen.baseVersion,
        branch="issue-17-other",
        testVersion="1.2.3-issue.17.0.1",
        testSHA=SHA2,
        candidateTag="v1.2.3-issue.17.0.1",
        result=sixteen.result,
        runner=sixteen.runner,
      )
      self.assertNotEqual(append_record(root, sixteen), append_record(root, seventeen))

  def test_schema_rejects_base_version_mismatch(self):
    broken = ValidationRecord(
      timestamp="2026-10-01T22:00:00Z",
      kind="regression",
      baseVersion="9.9.9",
      branch="issue-16-validation-audit",
      testVersion="1.2.3-issue.16.0.1",
      testSHA=SHA1,
      candidateTag=None,
      result="succeeded",
      runner="local",
    )
    with self.assertRaises(ValidationAuditError):
      broken.validate()

  def test_schema_rejects_extra_or_missing_fields(self):
    text = record().to_json().replace(
      '"runner":"local"',
      '"runner":"local","suite":"all"',
    )
    with self.assertRaises(ValidationAuditError):
      ValidationRecord.from_json(text)


if __name__ == "__main__":
  unittest.main()
