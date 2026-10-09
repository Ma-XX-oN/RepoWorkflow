"""Real Git tests for hosted terminal version/provider binding."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.hosted_terminal_binding import (
  HostedTerminalError, bind_hosted_terminal,
)


VERSION = "0.1.121-issue.572.0.1"


class HostedTerminalBindingTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    self.git("init", "-qb", "issue-572-cert")
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "source.py").write_text("source = 1\n")
    self.git("add", ".")
    self.git("commit", "-qm", "tested source")
    self.candidate = self.git("rev-parse", "HEAD")
    request = self.root / ".ci/run"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text("integration-testing " + self.candidate + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "test: request hosted integration")
    self.invocation = self.git("rev-parse", "HEAD")
    self.log = self.root / ".repoworkflow/validation/testResults-572.jsonl"
    self.log.parent.mkdir(parents=True, exist_ok=True)

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def record(self, **changes):
    value = {
      "runner": "github-actions", "branch": "issue-572-cert",
      "kind": "integration", "result": "succeeded",
      "testVersion": VERSION, "testSHA": self.candidate,
      "providerCandidateSHA": self.candidate,
      "providerInvocationSHA": self.invocation,
      "providerRunId": 123,
      "providerStage": "integration-testing",
      "headChangedDuringTest": False, "uncommittedChanges": [],
      "reusable": True,
    }
    value.update(changes)
    self.log.write_text(json.dumps(value) + "\n")

  def bind(self, **changes):
    args = {
      "root": self.root, "stage": "integration-testing",
      "candidate": self.candidate, "invocation": self.invocation,
      "run_id": 123, "canonical_log": self.log,
    }
    args.update(changes)
    return bind_hosted_terminal(**args)

  def test_integration_pass_returns_exact_prepared_tag_identity(self):
    self.record()
    self.assertEqual(self.bind(), {
      "stage": "integration", "version": VERSION,
      "candidate": self.candidate, "outcome": "PASS",
    })

  def test_genuine_fail_returns_failure_outcome(self):
    self.record(result="failed", reusable=False)
    self.assertEqual(self.bind()["outcome"], "FAIL")

  def test_incomplete_does_not_generate_terminal_tag_inputs(self):
    self.record(result="incomplete", reusable=False)
    with self.assertRaisesRegex(HostedTerminalError, "no authoritative"):
      self.bind()

  def test_missing_version_fails_closed(self):
    self.record(testVersion=None)
    with self.assertRaisesRegex(HostedTerminalError, "no authoritative"):
      self.bind()

  def test_wrong_provider_run_is_rejected(self):
    self.record(providerRunId=321)
    with self.assertRaisesRegex(HostedTerminalError, "providerRunId"):
      self.bind()

  def test_wrong_provider_invocation_is_rejected(self):
    self.record(providerInvocationSHA="f" * 40)
    with self.assertRaisesRegex(HostedTerminalError, "providerInvocationSHA"):
      self.bind()

  def test_wrong_candidate_is_rejected(self):
    self.record()
    with self.assertRaisesRegex(HostedTerminalError, "candidate"):
      self.bind(candidate="f" * 40)

  def test_dirty_pass_cannot_publish(self):
    self.record(uncommittedChanges=["source.py"])
    with self.assertRaises(HostedTerminalError):
      self.bind()

  def test_wrong_branch_version_evidence_fails_closed(self):
    self.record(branch="issue-573-other")
    with self.assertRaisesRegex(HostedTerminalError, "ancestry/evidence"):
      self.bind()

  def test_nonterminal_stage_is_rejected(self):
    self.record()
    with self.assertRaisesRegex(HostedTerminalError, "not terminal"):
      self.bind(stage="GREEN-testing")

  def test_malformed_log_is_rejected(self):
    self.log.write_text("{invalid\n")
    with self.assertRaises(HostedTerminalError):
      self.bind()


if __name__ == "__main__":
  unittest.main()
