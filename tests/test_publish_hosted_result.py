"""Real-Git publication tests for canonical hosted result logs."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish-hosted-result.py"


class PublishHostedResultTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    base = Path(self.tmp.name)
    self.remote = base / "remote.git"
    self.root = base / "work"
    self._run(base, "git", "init", "--bare", str(self.remote))
    self._run(base, "git", "init", "-b", "issue-543-probe", str(self.root))
    self._git("config", "user.email", "test@example.com")
    self._git("config", "user.name", "Test")
    (self.root / "test.txt").write_text("candidate")
    self._git("add", "test.txt")
    self._git("commit", "-m", "candidate")
    self.candidate = self._git("rev-parse", "HEAD")
    self._git("remote", "add", "origin", str(self.remote))
    self._git("push", "origin", "HEAD:refs/heads/issue-543-probe")
    marker = self.root / ".ci/run"
    marker.parent.mkdir()
    marker.write_text("GREEN-testing " + self.candidate + "\n")
    self._git("add", ".ci/run")
    self._git("commit", "-m", "invoke")
    self.invocation = self._git("rev-parse", "HEAD")
    self._git("push", "origin", "HEAD:refs/heads/issue-543-probe")
    self._git("reset", "--hard", self.candidate)
    self.log = self.root / ".repoworkflow/validation/testResults-543.jsonl"
    self.log.parent.mkdir(parents=True)
    self.observation = {
      "kind": "GREEN", "testSHA": self.candidate,
      "result": "succeeded", "runner": "local",
      "reusable": True, "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "groups": [{"group": "issue-543-demo", "exit_code": 0}],
    }
    self._record()

  def _run(self, cwd, *args):
    p = subprocess.run(
      list(args), cwd=cwd, text=True, capture_output=True, check=False,
    )
    if p.returncode:
      raise AssertionError(p.stderr + p.stdout)
    return p.stdout.strip()

  def _git(self, *args):
    return self._run(self.root, "git", *args)

  def _record(self):
    self.log.write_text(json.dumps(self.observation) + "\n")

  def _publish(self, **kw):
    return subprocess.run([
      sys.executable, str(SCRIPT), kw.get("stage", "GREEN-testing"),
      kw.get("candidate", self.candidate),
      "issue-543-probe", kw.get("invocation", self.invocation), "123",
    ], cwd=self.root, text=True, capture_output=True, check=False)

  def test_provider_publication_updates_only_results_log(self):
    result = self._publish()
    self.assertEqual(result.returncode, 0, result.stderr)
    remote = self._git("ls-remote", "origin", "refs/heads/issue-543-probe")
    published = remote.split()[0]
    self.assertEqual(self._git("rev-parse", "HEAD"), published)
    self.assertEqual(self._git("rev-parse", "HEAD^"), self.invocation)
    changed = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    self.assertEqual(changed, ".repoworkflow/validation/testResults-543.jsonl")
    record = json.loads(self.log.read_text().splitlines()[-1])
    self.assertEqual(record["runner"], "github-actions")
    self.assertEqual(record["providerRunId"], 123)
    self.assertEqual(record["providerCandidateSHA"], self.candidate)

  def test_publication_appends_to_already_tracked_results_log(self):
    # Second hosted run: candidate already contains published test observations.
    self._git("add", ".repoworkflow/validation/testResults-543.jsonl")
    self._git("commit", "-m", "previous accepted result")
    self.candidate = self._git("rev-parse", "HEAD")
    marker = self.root / ".ci/run"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text("GREEN-testing " + self.candidate + "\n")
    self._git("add", ".ci/run")
    self._git("commit", "-m", "invoke second test")
    self.invocation = self._git("rev-parse", "HEAD")
    # Fixture-only force push replaces the earlier synthetic invocation.
    self._git("push", "--force", "origin", "HEAD:refs/heads/issue-543-probe")
    self._git("reset", "--hard", self.candidate)
    self.observation["testSHA"] = self.candidate
    self._record()
    result = self._publish()
    self.assertEqual(result.returncode, 0, result.stderr)
    record = json.loads(self.log.read_text().splitlines()[-1])
    self.assertEqual(record["providerCandidateSHA"], self.candidate)
    self.assertEqual(record["providerInvocationSHA"], self.invocation)
    self.assertEqual(self._git("rev-parse", "HEAD^"), self.invocation)

  def test_retry_publication_keeps_original_candidate(self):
    self._git("merge", "--ff-only", self.invocation)
    marker = self.root / ".ci/run"
    marker.write_text(
      "integration-testing " + self.invocation + "\n",
    )
    self._git("add", ".ci/run")
    self._git("commit", "-m", "retry hosted integration")
    retry = self._git("rev-parse", "HEAD")
    self._git("push", "origin", "HEAD:refs/heads/issue-543-probe")
    self._git("reset", "--hard", self.candidate)
    self.observation["kind"] = "integration"
    self._record()
    result = self._publish(stage="integration-testing", invocation=retry)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self._git("rev-parse", "HEAD^"), retry)
    record = json.loads(self.log.read_text().splitlines()[-1])
    self.assertEqual(record["providerCandidateSHA"], self.candidate)
    self.assertNotEqual(record["providerCandidateSHA"], self.invocation)

  def test_stale_remote_branch_rejected_without_publication(self):
    self._git("merge", "--ff-only", self.invocation)
    other = self.root / "other.txt"
    other.write_text("later")
    self._git("add", "other.txt")
    self._git("commit", "-m", "move local")
    self._git("push", "origin", "HEAD:refs/heads/issue-543-probe")
    self._git("reset", "--hard", self.candidate)
    old = self._git("rev-parse", "HEAD")
    result = self._publish()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("remote branch moved", result.stderr)
    self.assertEqual(self._git("rev-parse", "HEAD"), old)

  def test_mismatched_candidate_rejected(self):
    self.observation["testSHA"] = "f" * 40
    self._record()
    result = self._publish()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("latest observation", result.stderr)
    self.assertEqual(self._git("rev-parse", "HEAD"), self.candidate)

  def test_dirty_source_rejected(self):
    (self.root / "extra.txt").write_text("dirty")
    result = self._publish()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("side effects", result.stderr)


if __name__ == "__main__":
  unittest.main()
