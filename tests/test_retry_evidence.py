"""Git-backed local retry evidence isolation contract tests."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.retry_evidence import (
  RetryEvidenceError, isolate_retry_evidence,
)


class RetryEvidenceTests(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.root = Path(tmp.name) / "repo"
    self.root.mkdir()
    self.git("init", "-b", "issue-569-check")
    self.git("config", "user.name", "Tester")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "source.txt").write_text("source\n")
    self.git("add", ".")
    self.git("commit", "-qm", "source")
    self.log = self.root / ".repoworkflow/validation/testResults-569.jsonl"
    self.log.parent.mkdir(parents=True)

  def git(self, *args):
    result = subprocess.run(
      ["git", "-C", str(self.root), *args], text=True,
      capture_output=True, check=True,
    )
    return result.stdout.strip()

  def write_record(self):
    self.log.write_text(json.dumps({
      "testSHA": self.git("rev-parse", "HEAD"),
      "kind": "regression", "result": "incomplete", "runner": "local",
    }) + "\n")

  def test_untracked_log_temporarily_hidden_then_restored(self):
    self.write_record()
    original = self.log.read_bytes()
    with isolate_retry_evidence(self.root, 569):
      self.assertFalse(self.log.exists())
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_tracked_log_restored_to_committed_contents_then_recovered(self):
    self.write_record()
    self.git("add", ".")
    self.git("commit", "-qm", "baseline log")
    self.log.write_text(self.log.read_text() + json.dumps(
      {"testSHA": self.git("rev-parse", "HEAD"),
       "kind": "regression", "result": "incomplete", "runner": "local",
       "attempt": 2}
    ) + "\n")
    original = self.log.read_bytes()
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(len(self.log.read_text().splitlines()), 1)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_dirty_source_rejected_without_changing_log(self):
    self.write_record()
    original = self.log.read_bytes()
    (self.root / "source.txt").write_text("dirty\n")
    with self.assertRaisesRegex(RetryEvidenceError, "dirty"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("must not enter")
    self.assertEqual(self.log.read_bytes(), original)

  def test_staged_log_change_is_rejected(self):
    self.write_record()
    self.git("add", ".repoworkflow/validation/testResults-569.jsonl")
    with self.assertRaisesRegex(RetryEvidenceError, "dirty"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("staged index must never be hidden")
    self.assertTrue(self.log.exists())

  def test_symlink_replacement_inside_context_restores_original_evidence(self):
    self.write_record()
    original = self.log.read_bytes()
    target = self.root.parent / "outside.txt"
    target.write_text("foreign\n")
    with self.assertRaisesRegex(RetryEvidenceError, "symlink"):
      with isolate_retry_evidence(self.root, 569):
        self.log.symlink_to(target)
    self.assertFalse(self.log.is_symlink())
    self.assertEqual(self.log.read_bytes(), original)
    self.assertEqual(target.read_text(), "foreign\n")

  def test_valid_json_with_missing_fields_is_rejected(self):
    self.log.write_text(json.dumps({"result": "incomplete"}) + "\n")
    with self.assertRaisesRegex(RetryEvidenceError, "incomplete"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("missing required provenance must fail")

  def test_empty_evidence_is_rejected(self):
    self.log.write_text("")
    with self.assertRaisesRegex(RetryEvidenceError, "empty"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("empty evidence must fail")

  def test_malformed_log_is_not_hidden(self):
    self.log.write_text("{broken\n")
    with self.assertRaisesRegex(RetryEvidenceError, "invalid"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("must not enter")
    self.assertTrue(self.log.exists())

  def test_symlink_log_rejected(self):
    target = self.root / "target"
    target.write_text("{}\n")
    self.log.symlink_to(target)
    with self.assertRaisesRegex(RetryEvidenceError, "symlink"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("must not enter")

  def test_exception_restores_original_log(self):
    self.write_record()
    original = self.log.read_bytes()
    with self.assertRaisesRegex(RuntimeError, "failure"):
      with isolate_retry_evidence(self.root, 569):
        raise RuntimeError("failure")
    self.assertEqual(self.log.read_bytes(), original)

  def test_operation_writing_new_evidence_fails_closed_without_data_loss(self):
    self.write_record()
    original = self.log.read_bytes()
    changed = json.dumps({"result": "unexpected"}) + "\n"
    with self.assertRaisesRegex(RetryEvidenceError, "changed"):
      with isolate_retry_evidence(self.root, 569):
        self.log.write_text(changed)
    self.assertEqual(self.log.read_bytes(), original)
    conflicts = list(self.log.parent.glob(self.log.name + ".retry-conflict-*"))
    self.assertEqual(len(conflicts), 1)
    self.assertEqual(conflicts[0].read_text(), changed)


  def record_bytes(self, runner="local", attempt=None):
    record = {
      "testSHA": self.git("rev-parse", "HEAD"),
      "kind": "regression", "result": "incomplete", "runner": runner,
    }
    if attempt is not None:
      record["attempt"] = attempt
    return json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"

  def git_blob(self, *args):
    return subprocess.run(
      ["git", "-C", str(self.root), *args],
      capture_output=True, check=True,
    ).stdout

  def test_raw_committed_crlf_preserved_without_text_roundtrip(self):
    self.git("config", "core.autocrlf", "false")
    (self.root / ".gitattributes").write_text(
      ".repoworkflow/validation/*.jsonl -text\n"
    )
    baseline = self.record_bytes().replace(b"\n", b"\r\n")
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "raw CRLF evidence")
    self.assertEqual(self.git_blob(
      "show", "HEAD:.repoworkflow/validation/testResults-569.jsonl"
    ), baseline)
    original = baseline + self.record_bytes(attempt=2).replace(b"\n", b"\r\n")
    self.log.write_bytes(original)
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(self.log.read_bytes(), baseline)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_lf_blob_crlf_checkout_filter(self):
    self.git("config", "core.autocrlf", "true")
    (self.root / ".gitattributes").write_text(
      ".repoworkflow/validation/*.jsonl text eol=crlf\n"
    )
    baseline = self.record_bytes()
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "LF evidence")
    self.assertEqual(self.git_blob(
      "show", "HEAD:.repoworkflow/validation/testResults-569.jsonl"
    ), baseline)
    self.log.unlink()
    self.git("checkout-index", "--", ".repoworkflow/validation/testResults-569.jsonl")
    expected = baseline.replace(b"\n", b"\r\n")
    self.assertEqual(self.log.read_bytes(), expected)
    self.git("add", ".repoworkflow/validation/testResults-569.jsonl")
    self.assertEqual(self.git("status", "--porcelain"), "")
    original = expected + self.record_bytes(attempt=2).replace(b"\n", b"\r\n")
    self.log.write_bytes(original)
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(self.log.read_bytes(), expected)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_implicit_autocrlf_does_not_leave_tracked_log_dirty(self):
    # Simulate Git for Windows' default without changing .gitattributes.
    self.git("config", "core.autocrlf", "true")
    baseline = self.record_bytes(runner="東京-é-🧪")
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "original LF worktree evidence")
    self.log.write_bytes(baseline + self.record_bytes(attempt=2))
    original = self.log.read_bytes()
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(self.log.read_bytes(), baseline)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)
    self.assertNotEqual(self.git("status", "--porcelain"), "")

  def test_implicit_autocrlf_with_clean_smudge_stays_clean(self):
    self.git("config", "core.autocrlf", "true")
    self.test_clean_smudge_roundtrip_filter()

  def test_clean_smudge_roundtrip_filter(self):
    import sys
    executable = '"' + sys.executable + '"'
    self.git("config", "filter.evidence.clean",
      executable + ' -c "import sys;sys.stdout.buffer.write('
      'sys.stdin.buffer.read().replace(b\'worktree\',b\'committed\'))"')
    self.git("config", "filter.evidence.smudge",
      executable + ' -c "import sys;sys.stdout.buffer.write('
      'sys.stdin.buffer.read().replace(b\'committed\',b\'worktree\'))"')
    (self.root / ".gitattributes").write_text(
      ".repoworkflow/validation/*.jsonl filter=evidence\n"
    )
    baseline = self.record_bytes(runner="worktree")
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "filtered evidence")
    self.assertIn(b'committed', self.git_blob(
      "show", "HEAD:.repoworkflow/validation/testResults-569.jsonl"
    ))
    self.log.write_bytes(baseline + self.record_bytes(attempt=2))
    original = self.log.read_bytes()
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(self.log.read_bytes(), baseline)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_unicode_raw_bytes_preserved(self):
    baseline = self.record_bytes(runner="東京-é-🧪")
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "Unicode evidence")
    self.log.write_bytes(baseline + self.record_bytes(attempt=2))
    original = self.log.read_bytes()
    with isolate_retry_evidence(self.root, 569):
      self.assertEqual(self.log.read_bytes(), baseline)
      self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.log.read_bytes(), original)

  def test_tracked_staged_log_is_rejected(self):
    self.write_record()
    self.git("add", ".")
    self.git("commit", "-qm", "tracked log")
    self.log.write_bytes(self.log.read_bytes() + self.record_bytes(attempt=2))
    self.git("add", ".repoworkflow/validation/testResults-569.jsonl")
    with self.assertRaisesRegex(RetryEvidenceError, "dirty"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("must reject staged tracked evidence")

  def test_unrelated_untracked_file_is_not_hidden(self):
    self.write_record()
    (self.root / "unrelated.txt").write_text("untrusted\n")
    with self.assertRaisesRegex(RetryEvidenceError, "dirty"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("must not enter")

  def test_wrong_issue_keeps_actual_dirty_log_visible(self):
    self.write_record()
    with isolate_retry_evidence(self.root, 570):
      self.assertTrue(self.log.exists())
      self.assertNotEqual(self.git("status", "--porcelain"), "")

  def test_multiple_jsonl_records_restore_exactly(self):
    original = self.record_bytes() + self.record_bytes(attempt=2)
    self.log.write_bytes(original)
    with isolate_retry_evidence(self.root, 569):
      self.assertFalse(self.log.exists())
    self.assertEqual(self.log.read_bytes(), original)

  def test_unrelated_mutation_inside_context_is_reported(self):
    self.write_record()
    original = self.log.read_bytes()
    with self.assertRaisesRegex(RetryEvidenceError, "dirtied"):
      with isolate_retry_evidence(self.root, 569):
        (self.root / "source.txt").write_text("dirty inside\n")
    self.assertEqual(self.log.read_bytes(), original)
    self.assertEqual((self.root / "source.txt").read_text(), "dirty inside\n")

  def test_tracked_context_conflict_preserves_exact_bytes(self):
    baseline = self.record_bytes()
    self.log.write_bytes(baseline)
    self.git("add", ".")
    self.git("commit", "-qm", "tracked evidence")
    self.log.write_bytes(baseline + self.record_bytes(attempt=2))
    original = self.log.read_bytes()
    conflict_bytes = b"untrusted\r\n"
    with self.assertRaisesRegex(RetryEvidenceError, "changed"):
      with isolate_retry_evidence(self.root, 569):
        self.log.write_bytes(conflict_bytes)
    self.assertEqual(self.log.read_bytes(), original)
    conflicts = list(self.log.parent.glob(self.log.name + ".retry-conflict-*"))
    self.assertEqual(len(conflicts), 1)
    self.assertEqual(conflicts[0].read_bytes(), conflict_bytes)

  def test_deleting_tracked_log_inside_context_is_reported(self):
    self.write_record()
    self.git("add", ".")
    self.git("commit", "-qm", "tracked evidence")
    self.log.write_bytes(self.log.read_bytes() + self.record_bytes(attempt=2))
    original = self.log.read_bytes()
    with self.assertRaisesRegex(RetryEvidenceError, "changed"):
      with isolate_retry_evidence(self.root, 569):
        self.log.unlink()
    self.assertEqual(self.log.read_bytes(), original)

  def test_invalid_utf8_jsonl_rejected(self):
    self.log.write_bytes(b'{"testSHA":"x","kind":"test","result":"incomplete",'
                         b'"runner":"\xff"}\n')
    with self.assertRaisesRegex(RetryEvidenceError, "invalid"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("invalid bytes must not be hidden")

  def test_status_inspection_failure_still_restores(self):
    from unittest.mock import patch
    self.write_record()
    original = self.log.read_bytes()
    with patch("repo_workflow.retry_evidence._status",
               side_effect=[[], [], RetryEvidenceError("cannot inspect candidate worktree")]):
      with self.assertRaisesRegex(RetryEvidenceError, "inspect"):
        with isolate_retry_evidence(self.root, 569):
          pass
    self.assertEqual(self.log.read_bytes(), original)


  def test_symlinked_parent_directory_is_rejected(self):
    outside = self.root.parent / "external-parent"
    outside.mkdir()
    self.log.parent.rmdir()
    try:
      self.log.parent.symlink_to(outside, target_is_directory=True)
    except OSError as error:
      self.skipTest(f"directory symlinks unavailable: {error}")
    (outside / self.log.name).write_bytes(self.record_bytes())
    with self.assertRaisesRegex(RetryEvidenceError, "parent"):
      with isolate_retry_evidence(self.root, 569):
        self.fail("symlinked canonical parent must never be followed")
    self.assertEqual((outside / self.log.name).read_bytes(), self.record_bytes())

  def test_parent_symlink_substitution_preserves_external_target(self):
    self.write_record()
    original = self.log.read_bytes()
    outside = self.root.parent / "external-parent"
    outside.mkdir()
    with self.assertRaisesRegex(RetryEvidenceError, "parent"):
      with isolate_retry_evidence(self.root, 569):
        self.log.parent.rmdir()
        try:
          self.log.parent.symlink_to(outside, target_is_directory=True)
        except OSError as error:
          self.skipTest(f"directory symlinks unavailable: {error}")
    self.assertEqual(self.log.read_bytes(), original)
    self.assertEqual(list(outside.iterdir()), [])
    conflicts = list(self.log.parent.parent.glob("validation.retry-conflict-*"))
    self.assertEqual(len(conflicts), 1)
    self.assertTrue((conflicts[0] / "validation").is_symlink())


if __name__ == "__main__":
  unittest.main()
