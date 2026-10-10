"""Black-box Git publication and independently supplied provider authority."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

from repo_workflow.hosted_cache import verified_hosted_passes


class HostedCacheTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.git("init", "-qb", "issue-545-cache")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    (self.root / "README").write_text("source\n")
    self.git("add", "README")
    self.git("commit", "-qm", "source")
    self.candidate = self.git("rev-parse", "HEAD")
    self.fingerprint = "a" * 64
    self.first_invocation = self.invoke("GREEN-testing")
    self.record = {
      "branch": "issue-545-cache",
      "kind": "GREEN",
      "result": "succeeded",
      "reusable": True,
      "runner": "github-actions",
      "testSHA": self.candidate,
      "providerCandidateSHA": self.candidate,
      "providerInvocationSHA": self.first_invocation,
      "providerRunId": 1234,
      "providerStage": "GREEN-testing",
      "catalogueSHA256": self.fingerprint,
      "headChangedDuringTest": False,
      "uncommittedChanges": [],
      "platform": {
        "os": platform.system(), "architecture": platform.machine(),
        "runtime": platform.python_version(),
      },
      "groups": [{"group": "issue-545-one", "exit_code": 0}],
    }
    self.remote = {
      "id": 1234, "status": "completed", "conclusion": "success",
      "head_sha": self.first_invocation,
      "head_branch": "issue-545-cache", "event": "push",
      "path": "Ma-XX-oN/RepoWorkflow/.github/workflows/on-demand-ci.yml",
    }

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
      stderr=subprocess.DEVNULL,
    ).strip()

  def invoke(self, stage):
    marker = self.root / ".ci/run"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(stage + " " + self.git("rev-parse", "HEAD") + "\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "invoke")
    return self.git("rev-parse", "HEAD")

  def publish(self, *records, run_number=1234):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in records))
    self.git("add", str(path.relative_to(self.root)))
    self.git("commit", "-qm",
             f"test: publish hosted evidence from run {run_number}")
    self.second_invocation = self.invoke("GREEN-testing")

  def reusable(self, record_override=None, provider_override=None):
    if record_override is not None:
      self.publish(record_override)
    fake = dict(self.remote)
    if provider_override:
      fake.update(provider_override)
    return verified_hosted_passes(
      self.root, stage="GREEN", revision=self.candidate,
      fingerprint=self.fingerprint, invocation=self.second_invocation,
      branch="issue-545-cache", repository="Ma-XX-oN/RepoWorkflow",
      token="fixture-token", provider_lookup=lambda repo, run_id, token: fake,
    )

  def test_authenticated_exact_pass_is_reused(self):
    self.assertEqual(self.reusable(self.record), {"issue-545-one"})

  def test_malformed_provider_response_is_cache_miss(self):
    self.publish(self.record)
    for response in (None, [], "not a response", 123):
      with self.subTest(response=response):
        self.assertEqual(verified_hosted_passes(
          self.root, stage="GREEN", revision=self.candidate,
          fingerprint=self.fingerprint, invocation=self.second_invocation,
          branch="issue-545-cache", repository="Ma-XX-oN/RepoWorkflow",
          token="fixture-token", provider_lookup=lambda *args: response,
        ), set())

  def test_provider_incomplete_wrong_head_or_workflow_fails_closed(self):
    self.publish(self.record)
    for update in (
      {"conclusion": "failure"}, {"status": "in_progress"},
      {"head_sha": "f" * 40}, {"head_branch": "issue-545-other"},
      {"path": ".github/workflows/other.yml"}, {"event": "workflow_dispatch"},
    ):
      with self.subTest(update=update):
        self.assertEqual(self.reusable(provider_override=update), set())

  def test_forged_or_dirty_record_cannot_be_reused(self):
    for i, change in enumerate((
      {"runner": "local"}, {"providerRunId": 456},
      {"providerInvocationSHA": "f" * 40},
      {"testSHA": "f" * 40}, {"catalogueSHA256": "f" * 64},
      {"uncommittedChanges": ["README"]}, {"reusable": False},
      {"result": "failed"}, {"headChangedDuringTest": True},
    )):
      with self.subTest(change=change):
        if i:
          self.setUp()  # Each immutable publication fixture is independent.
        self.assertEqual(self.reusable({**self.record, **change}), set())

  def test_latest_same_group_failure_revokes_old_pass(self):
    self.publish(self.record, {**self.record,
      "result": "failed", "groups": [{"group": "issue-545-one", "exit_code": 1}]})
    self.assertEqual(self.reusable(), set())

  def test_two_groups_and_partial_failure(self):
    two = {**self.record, "groups": [
      {"group": "issue-545-one", "exit_code": 0},
      {"group": "issue-545-two", "exit_code": 0},
    ]}
    self.publish(two, {**self.record,
      "result": "failed",
      "groups": [{"group": "issue-545-two", "exit_code": 1}]})
    self.assertEqual(self.reusable(), {"issue-545-one"})

  def test_publication_run_must_match_provider_record(self):
    self.publish(self.record, run_number=4321)
    self.assertEqual(self.reusable(), set())

  def test_invocation_parent_must_be_original_candidate(self):
    forged = {**self.record}
    self.publish(forged)
    # Existing provider run identity alone must not authorise an unrelated
    # original-candidate ancestry.  The real Git parent is independently checked.
    self.candidate = "f" * 40
    self.assertEqual(self.reusable(), set())

  def test_first_request_without_publication_is_cache_miss(self):
    self.assertEqual(verified_hosted_passes(
      self.root, stage="GREEN", revision=self.candidate,
      fingerprint=self.fingerprint, invocation=self.first_invocation,
      branch="issue-545-cache", repository="Ma-XX-oN/RepoWorkflow",
      token="fixture-token", provider_lookup=lambda *args: self.remote,
    ), set())


if __name__ == "__main__":
  unittest.main()
