"""Integration tests of the Git acceptance transport against a bare remote."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.git_acceptance import (
  accept_git_candidate, push_if_parent, read_remote_tip,
)
from repo_workflow.pre_merge_gate import PreMergeGateError


class RemoteAcceptanceTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    base = Path(self.temp.name)
    self.remote = base / "remote.git"
    self.first = base / "first"
    self.second = base / "second"
    self.git(base, "init", "--bare", "-q", str(self.remote))
    self.git(base, "init", "-q", str(self.first))
    self.config(self.first)
    (self.first / "file").write_text("parent\n")
    self.git(self.first, "add", "file")
    self.git(self.first, "commit", "-qm", "parent")
    self.parent = self.git(self.first, "rev-parse", "HEAD")
    self.ref = "refs/heads/integration-test"
    self.git(self.first, "push", "-q", str(self.remote),
             self.parent + ":" + self.ref)
    self.git(base, "clone", "-q", str(self.remote), str(self.second))
    self.config(self.second)
    self.git(self.second, "checkout", "-q", self.parent)
    self.advance(self.first, "first")
    self.advance(self.second, "second")
    self.one = self.git(self.first, "rev-parse", "HEAD")
    self.two = self.git(self.second, "rev-parse", "HEAD")
    self.assertNotEqual(self.one, self.two)
    for root, candidate in ((self.first, self.one), (self.second, self.two)):
      self.record(root, candidate)

  def git(self, root, *args):
    return subprocess.check_output(
      ["git", "-C", str(root), *args], text=True,
    ).strip()

  def config(self, root):
    self.git(root, "config", "user.name", "Fixture")
    self.git(root, "config", "user.email", "fixture@example.invalid")

  def advance(self, root, value):
    (root / "file").write_text(value + "\n")
    self.git(root, "add", "file")
    self.git(root, "commit", "-qm", value)

  def record(self, root, sha):
    results = root / "results"
    results.mkdir()
    (results / "linux.json").write_text(json.dumps({
      "schema": 1, "environment": "linux", "version": "1.0.0",
      "commit": sha, "status": "PASS",
    }))
    log = root / ".repoworkflow/validation/testResults-542.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({
      "kind": "integration", "testSHA": sha,
      "result": "succeeded", "runner": "local", "reusable": True,
      "uncommittedChanges": [], "headChangedDuringTest": False,
      "platform": {"os": "Linux", "architecture": "x86_64",
                   "runtime": "3.13"},
    }) + "\n")

  def accept(self, root, sha, **kwargs):
    args = {
      "remote": str(self.remote), "destination_ref": self.ref,
      "candidate_sha": sha, "recorded_parent_tip": self.parent,
      "server_protection_verified": True, "results_dir": root / "results",
      "config": {"environments": [{"id": "linux", "required": True}]},
      "version": "1.0.0",
      "canonical_log": root / ".repoworkflow/validation/testResults-542.jsonl",
      "required_platforms": ("Linux",),
    }
    args.update(kwargs)
    return accept_git_candidate(root, **args)

  def tip(self):
    return read_remote_tip(self.first, str(self.remote), self.ref)

  def test_first_wins_and_second_is_rejected_by_actual_git_remote(self):
    self.accept(self.first, self.one)
    self.assertEqual(self.tip(), self.one)
    with self.assertRaisesRegex(PreMergeGateError, "tip advanced"):
      self.accept(self.second, self.two)
    self.assertEqual(self.tip(), self.one)

  def test_two_real_remote_writers_race_same_expected_tip(self):
    actual_read = read_remote_tip
    barrier = threading.Barrier(2)
    results = []

    def simultaneous_read(root, remote, ref):
      tip = actual_read(root, remote, ref)
      barrier.wait(timeout=5)
      return tip

    def worker(root, candidate):
      try:
        self.accept(root, candidate)
        return "accepted"
      except PreMergeGateError:
        return "rejected"

    with patch("repo_workflow.git_acceptance.read_remote_tip",
               side_effect=simultaneous_read):
      with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
          lambda pair: worker(*pair),
          ((self.first, self.one), (self.second, self.two)),
        ))
    self.assertEqual(sorted(results), ["accepted", "rejected"])
    self.assertIn(self.tip(), (self.one, self.two))

  def test_lost_lease_after_preflight_is_rejected_without_mutation(self):
    with patch("repo_workflow.git_acceptance.push_if_parent") as cas:
      def accept(root, remote, ref, candidate, expected):
        # Another actor advances the real remote immediately before CAS.
        self.assertTrue(push_if_parent(
          self.second, str(self.remote), self.ref, self.two, self.parent,
        ))
        return push_if_parent(
          self.first, str(self.remote), self.ref, candidate, expected,
        )
      cas.side_effect = accept
      with self.assertRaisesRegex(PreMergeGateError, "remote rejected"):
        self.accept(self.first, self.one)
    self.assertEqual(self.tip(), self.two)

  def test_unverified_protection_rejects_before_remote_write(self):
    with self.assertRaisesRegex(PreMergeGateError, "protection"):
      self.accept(self.first, self.one, server_protection_verified=False)
    self.assertEqual(self.tip(), self.parent)

  def test_main_cannot_be_updated_with_the_raw_git_transport(self):
    with self.assertRaisesRegex(PreMergeGateError, "GitHub PR merge gate"):
      self.accept(self.first, self.one, destination_ref="refs/heads/main")
    self.assertEqual(self.tip(), self.parent)

  def test_missing_destination_and_invalid_refs_fail_closed(self):
    with self.assertRaises(PreMergeGateError):
      self.accept(self.first, self.one, destination_ref="refs/heads/missing")
    with self.assertRaises(PreMergeGateError):
      self.accept(self.first, self.one, destination_ref="refs/heads/../main")
    self.assertEqual(self.tip(), self.parent)

  def test_dirty_or_failed_logs_prevent_remote_mutation(self):
    path = self.first / "results/linux.json"
    data = json.loads(path.read_text())
    data["status"] = "FAIL"
    path.write_text(json.dumps(data))
    with self.assertRaises(PreMergeGateError):
      self.accept(self.first, self.one)
    self.assertEqual(self.tip(), self.parent)


if __name__ == "__main__":
  unittest.main()
