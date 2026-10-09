"""Real-Git engine version preparation contract tests."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.engine_remote import (
  EnginePreparationError, prepare_engine_request,
)


class EngineRemotePreparationTests(unittest.TestCase):
  def setUp(self):
    self.t = tempfile.TemporaryDirectory()
    self.addCleanup(self.t.cleanup)
    self.root = Path(self.t.name) / "source"
    self.root.mkdir()
    self.remote = Path(self.t.name) / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(self.remote)])
    self.git("init", "-qb", "issue-572-work")
    self.git("config", "user.name", "Tester")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "VERSION").write_text("0.1.121\n")
    self.git("add", ".")
    self.git("commit", "-qm", "stable source")
    self.git("remote", "add", "origin", str(self.remote))

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def prepare(self, stage="regression"):
    return prepare_engine_request(
      self.root, stage=stage, issue=572,
    )

  def publish(self, name):
    self.git("tag", "-a", name, "-m", name)
    self.git("push", "-q", "origin", "refs/tags/" + name)

  def test_first_request_prepares_committed_dev_version(self):
    previous = self.git("rev-parse", "HEAD")
    self.assertEqual(self.prepare(), "0.1.121-issue.572.0.1")
    self.assertNotEqual(self.git("rev-parse", "HEAD"), previous)
    self.assertEqual(
      self.git("show", "HEAD:.ci/engine-version"),
      "0.1.121-issue.572.0.1",
    )

  def test_same_stage_retry_does_not_bump_without_terminal_tag(self):
    first = self.prepare()
    candidate = self.git("rev-parse", "HEAD")
    self.assertEqual(self.prepare(), first)
    self.assertEqual(self.git("rev-parse", "HEAD"), candidate)

  def test_regression_fail_advances_r_for_next_regression(self):
    self.prepare()
    self.publish("v0.1.121-issue.572.0.1-CI-FAIL")
    self.assertEqual(self.prepare(), "0.1.121-issue.572.0.2")

  def test_integration_fail_advances_q_for_next_generation(self):
    self.prepare()
    self.publish("v0.1.121-PRELIM-572.0.1-CI-FAIL")
    self.assertEqual(self.prepare(), "0.1.121-issue.572.1.1")

  def test_integration_pass_never_increments_regression_r(self):
    self.prepare()
    self.publish("v0.1.121-issue.572.0.1")
    self.assertEqual(self.prepare("integration"), "0.1.121-issue.572.0.1")

  def test_invalid_stage_and_issue_never_change_history(self):
    original = self.git("rev-parse", "HEAD")
    for kwargs in (
      {"stage": "RED", "issue": 572},
      {"stage": "regression", "issue": 573},
      {"stage": "integration", "issue": 0},
    ):
      with self.subTest(kwargs=kwargs):
        with self.assertRaises(EnginePreparationError):
          prepare_engine_request(self.root, **kwargs)
        self.assertEqual(self.git("rev-parse", "HEAD"), original)

  def test_different_issue_version_rejected_without_mutation(self):
    self.prepare()
    before = self.git("rev-parse", "HEAD")
    self.git("checkout", "-qb", "issue-573-other")
    with self.assertRaises(EnginePreparationError):
      prepare_engine_request(
        self.root, stage="regression", issue=573,
      )
    self.assertEqual(self.git("rev-parse", "HEAD"), before)


if __name__ == "__main__":
  unittest.main()
