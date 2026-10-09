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
    self.log.write_text(json.dumps({"result": "incomplete"}) + "\n")

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
      {"result": "incomplete", "attempt": 2}
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


if __name__ == "__main__":
  unittest.main()
