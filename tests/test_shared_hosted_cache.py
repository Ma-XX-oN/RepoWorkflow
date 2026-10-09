"""Actual Git-backed shared hosted cache readback from candidate checkout."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.test_cli import run_test
from tests import test_test_cli as fixture


class SharedHostedCacheTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  remote = fixture.TestCliContract.remote
  _catalogue = fixture.TestCliContract._catalogue

  def prepare(self, *, stale=False):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-shared",
    )
    selected = self.root / ".ci/red-green.txt"
    selected.write_text("issue-545-shared\n")
    self.git("add", ".ci/tests.json", ".ci/red-green.txt", "smoke_case.py")
    self.git("commit", "-m", "committed selected group")
    candidate = self.git("rev-parse", "HEAD")
    bare = self.remote()
    publisher = Path(self.temp.name) / "publisher"
    subprocess.run(
      ["git", "clone", "-q", "--branch", "issue-545-fixture",
       str(bare), str(publisher)], check=True,
    )
    def publisher_git(*args):
      subprocess.run(["git", "-C", str(publisher), *args], check=True,
                     capture_output=True, text=True)
    publisher_git("config", "user.email", "provider@example.invalid")
    publisher_git("config", "user.name", "Provider")
    marker = publisher / ".ci/run"
    marker.write_text("GREEN-testing " + candidate + "\n")
    publisher_git("add", ".ci/run")
    publisher_git("commit", "-m", "requested stage")
    log = publisher / ".repoworkflow/validation/testResults-545.jsonl"
    log.parent.mkdir(parents=True)
    record = {
      "testSHA": ("f" * 40 if stale else candidate),
      "kind": "GREEN", "catalogueSHA256": hashlib.sha256(
        (self.root / ".ci/tests.json").read_bytes()
      ).hexdigest(),
      "runner": "github-actions", "result": "succeeded",
      "reusable": True, "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "platform": {
        "os": platform.system(), "architecture": platform.machine(),
        "runtime": platform.python_version(),
      },
      "groups": [{"group": "issue-545-shared", "exit_code": 0}],
    }
    log.write_text(json.dumps(record) + "\n")
    publisher_git("add", ".repoworkflow/validation/testResults-545.jsonl")
    publisher_git("commit", "-m", "publish verified result")
    publisher_git("push", "origin", "HEAD:issue-545-fixture")
    return candidate, bare

  def test_verified_remote_result_skips_rerunning_identical_test(self):
    candidate, bare = self.prepare()
    published_before = subprocess.check_output(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"], text=True,
    ).strip()
    with patch(
      "repo_workflow.test_cli.hosted_cache_checker",
      return_value=lambda record: record.get("runner") == "github-actions",
    ):
      status = run_test(
        self.root, "GREEN", remote=False, engine_root=self.root,
      )
    self.assertEqual(status, 0)
    self.assertEqual(self.git("rev-parse", "HEAD"), candidate)
    self.assertEqual(subprocess.check_output(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"], text=True,
    ).strip(), published_before)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    newest = json.loads(log.read_text().splitlines()[-1])
    self.assertTrue(newest["groups"][0]["reused"])
    self.assertEqual(newest["testSHA"], candidate)
    self.assertEqual(newest["runner"], "local")

  def test_remote_pass_without_provider_verification_is_not_reused(self):
    self.prepare()
    with patch(
      "repo_workflow.test_cli.hosted_cache_checker",
      return_value=lambda record: False,
    ):
      self.assertEqual(run_test(
        self.root, "GREEN", remote=False, engine_root=self.root,
      ), 0)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertFalse(json.loads(log.read_text().splitlines()[-1])[
      "groups"][0]["reused"])

  def test_mismatched_candidate_does_not_reuse_remote_pass(self):
    self.prepare(stale=True)
    with patch(
      "repo_workflow.test_cli.hosted_cache_checker",
      return_value=lambda record: True,
    ):
      self.assertEqual(run_test(
        self.root, "GREEN", remote=False, engine_root=self.root,
      ), 0)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertFalse(json.loads(log.read_text().splitlines()[-1])[
      "groups"][0]["reused"])


if __name__ == "__main__":
  unittest.main()
