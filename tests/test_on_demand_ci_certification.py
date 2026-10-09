from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from repo_workflow.ci_invocation import verify_invocation
from repo_workflow.pre_merge_gate import (
  PreMergeGateError,
  check_pre_merge_candidate,
)


class OnDemandCertificationTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    self.git("init", "-q")
    self.git("config", "user.name", "Test actor")
    self.git("config", "user.email", "actor@example.invalid")
    (self.root / "file.py").write_text("value = 1\n")
    self.git("add", "file.py")
    self.git("commit", "-qm", "main")
    self.main_tip = self.git("rev-parse", "HEAD")
    (self.root / "file.py").write_text("value = 2\n")
    self.git("add", "file.py")
    self.git("commit", "-qm", "integrated candidate")
    self.pre_invocation_tip = self.git("rev-parse", "HEAD")
    directory = self.root / ".ci"
    directory.mkdir()
    (directory / "run").write_text(
      "integration-testing " + self.pre_invocation_tip + "\n"
    )
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "request verification")
    self.tested_sha = self.git("rev-parse", "HEAD")
    self.results_dir = self.root / "results"
    self.results_dir.mkdir()
    self.config = {
      "environments": [{"id": "required", "required": True}],
    }

  def tearDown(self):
    self.tmp.cleanup()

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def log(self, tested_sha, status="PASS"):
    (self.results_dir / "required.json").write_text(json.dumps({
      "schema": 1,
      "environment": "required",
      "version": "1.0.0",
      "commit": tested_sha,
      "status": status,
    }), encoding="utf-8")

  def check(self, authoritative_tip):
    return check_pre_merge_candidate(
      self.root,
      candidate_sha=self.tested_sha,
      recorded_parent_tip=self.main_tip,
      authoritative_parent_tip=authoritative_tip,
      results_dir=self.results_dir,
      config=self.config,
      version="1.0.0",
    )

  def test_request_then_exact_logged_result_allows_preflight(self):
    marker = verify_invocation(self.root)
    self.assertEqual(marker.stage, "integration-testing")
    self.assertEqual(marker.previous_tip, self.pre_invocation_tip)
    self.log(self.tested_sha)
    self.assertIsNone(self.check(self.main_tip))

  def test_request_is_not_accepted_as_a_test_result(self):
    verify_invocation(self.root)
    with self.assertRaisesRegex(PreMergeGateError, "INCOMPLETE"):
      self.check(self.main_tip)

  def test_log_for_pre_invocation_tip_does_not_cover_request_commit(self):
    verify_invocation(self.root)
    self.log(self.pre_invocation_tip)
    with self.assertRaisesRegex(Exception, "commit does not match"):
      self.check(self.main_tip)

  def test_second_actor_advance_rejects_previously_green_candidate(self):
    verify_invocation(self.root)
    self.log(self.tested_sha)
    with self.assertRaisesRegex(PreMergeGateError, "tip advanced"):
      self.check(self.tested_sha)

  def test_retry_after_missed_event_requests_previous_tip(self):
    verify_invocation(self.root)
    previous_request = self.tested_sha
    (self.root / ".ci" / "run").write_text(
      "integration-testing " + previous_request + "\n"
    )
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "retry request")
    retry = verify_invocation(self.root)
    self.assertEqual(retry.previous_tip, previous_request)
    self.assertEqual(retry.stage, "integration-testing")
    self.assertNotEqual(self.git("rev-parse", "HEAD"), previous_request)


if __name__ == "__main__":
  unittest.main()
