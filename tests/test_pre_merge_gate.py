from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.pre_merge_gate import (
  PreMergeGateError,
  check_pre_merge_candidate,
)


class PreMergeGateTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    self.git("init", "-q")
    self.git("config", "user.email", "ci@example.invalid")
    self.git("config", "user.name", "CI Fixture")
    (self.root / "file.txt").write_text("base\n")
    self.git("add", "file.txt")
    self.git("commit", "-qm", "parent")
    self.parent = self.git("rev-parse", "HEAD")
    (self.root / "file.txt").write_text("candidate\n")
    self.git("add", "file.txt")
    self.git("commit", "-qm", "candidate")
    self.candidate = self.git("rev-parse", "HEAD")
    self.config = {
      "environments": [{"id": "linux", "required": True}],
    }
    self.results = self.root / "test-logs"
    self.results.mkdir()
    self.write_result("PASS")
    self.canonical_log = (
      self.root / ".repoworkflow/validation/testResults-542.jsonl"
    )
    self.canonical_log.parent.mkdir(parents=True)
    self.write_canonical("succeeded")

  def write_canonical(self, result):
    self.canonical_log.write_text(json.dumps({
      "kind": "integration",
      "testSHA": self.candidate,
      "result": result,
      "runner": "local",
      "reusable": result == "succeeded",
      "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "platform": {"os": "Linux"},
    }) + "\n")


  def tearDown(self):
    self.tmp.cleanup()

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def write_result(self, status, commit=None):
    (self.results / "linux.json").write_text(json.dumps({
      "schema": 1,
      "environment": "linux",
      "version": "1.0.0",
      "commit": commit or self.candidate,
      "status": status,
    }), encoding="utf-8")

  def check(self, **kwargs):
    values = {
      "candidate_sha": self.candidate,
      "recorded_parent_tip": self.parent,
      "authoritative_parent_tip": self.parent,
      "results_dir": self.results,
      "config": self.config,
      "version": "1.0.0",
      "canonical_log": self.canonical_log,
      "required_platforms": ("Linux",),
    }
    values.update(kwargs)
    return check_pre_merge_candidate(self.root, **values)

  def test_current_parent_and_exact_candidate_logs_pass(self):
    self.assertIsNone(self.check())

  def test_legacy_pass_without_canonical_record_is_rejected(self):
    self.canonical_log.unlink()
    with self.assertRaisesRegex(PreMergeGateError, "canonical"):
      self.check()

  def test_canonical_failure_blocks_even_if_legacy_passes(self):
    self.write_canonical("failed")
    with self.assertRaisesRegex(PreMergeGateError, "integration PASS"):
      self.check()

  def test_hosted_record_requires_verified_provider_lookup(self):
    record = json.loads(self.canonical_log.read_text())
    record.update({
      "runner": "github-actions",
      "providerRunId": 123,
      "providerCandidateSHA": self.candidate,
      "providerInvocationSHA": "b" * 40,
      "providerStage": "integration-testing",
    })
    self.canonical_log.write_text(json.dumps(record) + "\n")
    with self.assertRaisesRegex(PreMergeGateError, "integration PASS"):
      self.check()
    with patch(
      "repo_workflow.pre_merge_gate.verify_hosted_integration",
      return_value=False,
    ) as verify:
      with self.assertRaisesRegex(PreMergeGateError, "integration PASS"):
        self.check(provider_repo="Ma-XX-oN/RepoWorkflow")
      verify.assert_called_once()
    with patch(
      "repo_workflow.pre_merge_gate.verify_hosted_integration",
      return_value=True,
    ) as verify:
      self.check(provider_repo="Ma-XX-oN/RepoWorkflow")
      verify.assert_called_once()

  def test_second_actor_rejected_after_parent_advances(self):
    with self.assertRaisesRegex(PreMergeGateError, "tip advanced"):
      self.check(authoritative_parent_tip=self.candidate)

  def test_stale_logged_candidate_is_rejected(self):
    self.write_result("PASS", commit=self.parent)
    with self.assertRaisesRegex(Exception, "commit does not match"):
      self.check()

  def test_logged_fail_does_not_satisfy_gate(self):
    self.write_result("FAIL")
    with self.assertRaisesRegex(PreMergeGateError, "FAIL"):
      self.check()

  def test_missing_result_does_not_satisfy_gate(self):
    (self.results / "linux.json").unlink()
    with self.assertRaisesRegex(PreMergeGateError, "INCOMPLETE"):
      self.check()

  def test_candidate_moved_after_tests_is_rejected(self):
    (self.root / "file.txt").write_text("changed\n")
    self.git("add", "file.txt")
    self.git("commit", "-qm", "new candidate")
    with self.assertRaisesRegex(PreMergeGateError, "candidate SHA changed"):
      self.check()

  def test_candidate_not_based_on_recorded_parent_is_rejected(self):
    self.git("checkout", "-qb", "other", self.parent)
    (self.root / "file.txt").write_text("other\n")
    self.git("add", "file.txt")
    self.git("commit", "-qm", "other")
    other_sha = self.git("rev-parse", "HEAD")
    with self.assertRaisesRegex(PreMergeGateError, "excludes parent tip"):
      self.check(
        candidate_sha=other_sha,
        recorded_parent_tip=self.candidate,
        authoritative_parent_tip=self.candidate,
      )

  def test_invalid_shas_fail_closed(self):
    with self.assertRaisesRegex(PreMergeGateError, "invalid candidate SHA"):
      self.check(candidate_sha="HEAD")


if __name__ == "__main__":
  unittest.main()
