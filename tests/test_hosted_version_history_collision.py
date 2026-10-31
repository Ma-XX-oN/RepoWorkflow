"""Old immutable version collisions must not contaminate a distinct successor."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.hosted_version_identity import (
  HostedVersionError, resolve_hosted_version,
)


OLD = "0.1.122-issue.683.0.1"
NEW = "0.1.122-issue.683.0.2"


class HistoricalCollisionTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.git("init", "-q", "-b", "issue-683-history")
    self.git("config", "user.name", "Fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    self.log = (
      self.root / ".repoworkflow/validation/testResults-683.jsonl"
    )
    self.log.parent.mkdir(parents=True)
    self.candidates = []
    self.invocations = []
    for index, version, outcome in (
        (1, OLD, "failed"), (2, OLD, "succeeded"),
        (3, NEW, "succeeded")):
      (self.root / "source").write_text(str(index) + "\n")
      self.git("add", "source")
      self.git("commit", "-qm", "candidate " + str(index))
      candidate = self.git("rev-parse", "HEAD")
      self.candidates.append(candidate)
      marker = self.root / ".ci/run"
      marker.parent.mkdir(exist_ok=True)
      marker.write_text("regression-testing " + candidate + "\n")
      self.git("add", ".ci/run")
      self.git("commit", "-qm", "request " + str(index))
      self.invocations.append(self.git("rev-parse", "HEAD"))
      self.append(candidate, version, outcome)

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args], text=True,
    ).strip()

  def append(self, sha, version, outcome):
    record = {
      "testSHA": sha, "kind": "regression",
      "branch": "issue-683-history", "testVersion": version,
      "result": outcome, "runner": "github-actions",
      "headChangedDuringTest": False, "uncommittedChanges": [],
    }
    with self.log.open("a", encoding="utf-8") as stream:
      stream.write(json.dumps(record) + "\n")

  def test_distinct_new_version_survives_old_conflicted_outcomes(self):
    proof = resolve_hosted_version(
      self.root, self.invocations[2], self.log)
    self.assertEqual(proof["candidate_sha"], self.candidates[2])
    self.assertEqual(proof["test_version"], NEW)

  def test_historical_version_claim_is_still_rejected(self):
    with self.assertRaises(HostedVersionError):
      resolve_hosted_version(
        self.root, self.invocations[1], self.log)

  def test_conflicting_current_version_outcome_is_still_denied(self):
    self.append(self.candidates[2], NEW, "failed")
    with self.assertRaisesRegex(
        HostedVersionError, "conflicting terminal version outcomes"):
      resolve_hosted_version(
        self.root, self.invocations[2], self.log)

  def test_conflicting_new_version_owner_is_still_denied(self):
    self.append(self.candidates[1], NEW, "succeeded")
    with self.assertRaisesRegex(
        HostedVersionError, "different candidate"):
      resolve_hosted_version(
        self.root, self.invocations[2], self.log)


if __name__ == "__main__":
  unittest.main()
