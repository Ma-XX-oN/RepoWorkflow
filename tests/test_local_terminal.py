"""Real-Git acceptance for local terminal publication."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.local_terminal import publish_local_terminal
from repo_workflow.terminal_tag import TerminalTagError
from repo_workflow.engine_remote import prepare_engine_request

VERSION = "0.1.122-issue.572.0.1"


class LocalTerminalTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    base = Path(self.temp.name)
    self.root = base / "repo"
    self.remote = base / "remote.git"
    subprocess.run(["git", "init", "--bare", str(self.remote)],
                   check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "issue-572-cert", str(self.root)],
                   check=True, capture_output=True)
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "VERSION").write_text("0.1.122\n")
    self.git("add", "VERSION")
    self.git("commit", "-m", "source")
    self.git("remote", "add", "origin", str(self.remote))
    self.candidate = self.git("rev-parse", "HEAD")
    self.log = self.root / ".repoworkflow/validation/testResults-572.jsonl"
    self.log.parent.mkdir(parents=True)

  def git(self, *args):
    result = subprocess.run(
      ["git", "-C", str(self.root), *args],
      text=True, capture_output=True, check=False,
    )
    if result.returncode:
      raise AssertionError(result.stderr)
    return result.stdout.strip()

  def evidence(self, stage, result, *, version=VERSION):
    record = {
      "kind": stage, "branch": "issue-572-cert",
      "testSHA": self.candidate, "result": result,
      "testVersion": version, "runner": "local",
      "reusable": result == "succeeded",
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }
    with self.log.open("a", encoding="utf-8") as file:
      file.write(json.dumps(record) + "\n")

  def test_pass_creates_annotated_local_only_regression_tag(self):
    self.evidence("regression", "succeeded")
    tag = publish_local_terminal(self.root, stage="regression")
    self.assertEqual(tag, "v" + VERSION)
    self.assertEqual(self.git("cat-file", "-t", "refs/tags/" + tag), "tag")
    self.assertEqual(self.git("rev-parse", tag + "^{commit}"), self.candidate)
    self.assertEqual(self.git("ls-remote", "--tags", "origin"), "")
    original_object = self.git("rev-parse", "refs/tags/" + tag)
    self.assertEqual(publish_local_terminal(self.root, stage="regression"), tag)
    self.assertEqual(self.git("rev-parse", "refs/tags/" + tag), original_object)

  def test_integration_failure_uses_distinct_prelim_namespace(self):
    self.evidence("integration", "failed")
    tag = publish_local_terminal(self.root, stage="integration")
    self.assertEqual(tag, "v0.1.122-PRELIM-572.0.1-CI-FAIL")
    self.assertEqual(self.git("cat-file", "-t", "refs/tags/" + tag), "tag")
    self.assertEqual(self.git("rev-parse", tag + "^{commit}"), self.candidate)

  def test_incomplete_does_not_create_any_tag(self):
    self.evidence("regression", "incomplete", version=None)
    self.assertIsNone(publish_local_terminal(self.root, stage="regression"))
    self.assertEqual(self.git("tag", "--list"), "")

  def test_definitive_outcome_without_authoritative_version_refused(self):
    self.evidence("regression", "succeeded", version=None)
    with self.assertRaisesRegex(TerminalTagError, "authoritative"):
      publish_local_terminal(self.root, stage="regression")
    self.assertEqual(self.git("tag", "--list"), "")

  def test_wrong_stage_and_malformed_evidence_rejected(self):
    self.evidence("integration", "succeeded")
    with self.assertRaisesRegex(TerminalTagError, "not the terminal stage"):
      publish_local_terminal(self.root, stage="regression")
    self.log.write_text("{bad json\n")
    with self.assertRaisesRegex(TerminalTagError, "unavailable"):
      publish_local_terminal(self.root, stage="integration")

  def test_local_failure_tag_drives_next_explicit_r_transition(self):
    state = self.root / ".ci/engine-version"
    state.parent.mkdir()
    state.write_text(VERSION + "\n")
    self.git("add", ".ci/engine-version")
    self.git("commit", "-m", "prepared version")
    self.candidate = self.git("rev-parse", "HEAD")
    self.evidence("regression", "failed")
    self.assertEqual(
      publish_local_terminal(self.root, stage="regression"),
      "v" + VERSION + "-CI-FAIL",
    )
    self.assertEqual(
      prepare_engine_request(self.root, stage="regression", issue=572),
      "0.1.122-issue.572.0.2",
    )
    self.assertEqual(state.read_text(), "0.1.122-issue.572.0.2\n")


if __name__ == "__main__":
  unittest.main()
