"""Concurrency tests for atomic pre-merge destination acceptance."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from repo_workflow.pre_merge_gate import (
  PreMergeGateError,
  accept_pre_merge_candidate,
)


class AtomicPreMergeAcceptanceTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.base = Path(self.tmp.name)
    self.first = self.base / "first"
    self.second = self.base / "second"
    self.git("init", "-q", str(self.first))
    self.configure(self.first)
    (self.first / "file.txt").write_text("base\n", encoding="utf-8")
    self.run_git(self.first, "add", "file.txt")
    self.run_git(self.first, "commit", "-qm", "parent")
    self.parent = self.run_git(self.first, "rev-parse", "HEAD")
    self.run_git(self.first, "branch", "candidate-one")
    self.git("clone", "-q", str(self.first), str(self.second))
    self.configure(self.second)
    self.make_candidate(self.first, "one")
    self.make_candidate(self.second, "two")
    self.candidate_one = self.run_git(self.first, "rev-parse", "HEAD")
    self.candidate_two = self.run_git(self.second, "rev-parse", "HEAD")
    self.assertNotEqual(self.candidate_one, self.candidate_two)
    self.prepare_evidence(self.first, self.candidate_one)
    self.prepare_evidence(self.second, self.candidate_two)

  def git(self, *args):
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)

  def run_git(self, root, *args):
    return subprocess.check_output(
      ["git", "-C", str(root), *args], text=True,
    ).strip()

  def configure(self, root):
    self.run_git(root, "config", "user.email", "ci@example.invalid")
    self.run_git(root, "config", "user.name", "CI Fixture")

  def make_candidate(self, root, value):
    (root / "file.txt").write_text(value + "\n", encoding="utf-8")
    self.run_git(root, "add", "file.txt")
    self.run_git(root, "commit", "-qm", "candidate " + value)

  def prepare_evidence(self, root, candidate):
    results = root / "test-logs"
    results.mkdir()
    (results / "linux.json").write_text(json.dumps({
      "schema": 1,
      "environment": "linux",
      "version": "1.0.0",
      "commit": candidate,
      "status": "PASS",
    }), encoding="utf-8")
    canonical = root / ".repoworkflow/validation/testResults-542.jsonl"
    canonical.parent.mkdir(parents=True)
    canonical.write_text(json.dumps({
      "kind": "integration",
      "testSHA": candidate,
      "result": "succeeded",
      "runner": "local",
      "reusable": True,
      "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "platform": {
        "os": "Linux",
        "architecture": "x86_64",
        "runtime": "3.13",
      },
    }) + "\n", encoding="utf-8")

  def accept(self, root, candidate, read_tip, accept_if_parent):
    accept_pre_merge_candidate(
      root,
      candidate_sha=candidate,
      recorded_parent_tip=self.parent,
      read_authoritative_parent_tip=read_tip,
      accept_if_parent=accept_if_parent,
      results_dir=root / "test-logs",
      config={"environments": [{"id": "linux", "required": True}]},
      version="1.0.0",
      canonical_log=root / ".repoworkflow/validation/testResults-542.jsonl",
      required_platforms=("Linux",),
    )

  def test_second_racing_actor_is_rejected_before_destination_mutation(self):
    state = {"head": self.parent, "accepted": []}
    lock = threading.Lock()
    reads = threading.Barrier(2)

    def read_tip():
      with lock:
        observed = state["head"]
      reads.wait(timeout=5)
      return observed

    def accept_if_parent(candidate, expected):
      with lock:
        if state["head"] != expected:
          return False
        state["head"] = candidate
        state["accepted"].append(candidate)
        return True

    def run(root, candidate):
      try:
        self.accept(root, candidate, read_tip, accept_if_parent)
        return "accepted"
      except PreMergeGateError as error:
        return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
      results = list(pool.map(
        lambda args: run(*args),
        ((self.first, self.candidate_one), (self.second, self.candidate_two)),
      ))

    self.assertEqual(results.count("accepted"), 1)
    rejected = [item for item in results if item != "accepted"]
    self.assertEqual(len(rejected), 1)
    self.assertIn("destination tip advanced before acceptance", rejected[0])
    self.assertEqual(len(state["accepted"]), 1)
    self.assertEqual(state["head"], state["accepted"][0])

  def test_stale_parent_fails_before_acceptance_callback(self):
    called = []

    with self.assertRaisesRegex(PreMergeGateError, "tip advanced"):
      self.accept(
        self.first,
        self.candidate_one,
        lambda: self.candidate_two,
        lambda candidate, expected: called.append((candidate, expected)) or True,
      )

    self.assertEqual(called, [])


if __name__ == "__main__":
  unittest.main()
