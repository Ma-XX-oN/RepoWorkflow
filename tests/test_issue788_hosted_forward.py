"""Exact Git-history negative and positive tests for #788 GitHub forwarding."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hosted-rwf-forward.py"
SPEC = importlib.util.spec_from_file_location("rwf_hosted_forward_788", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hosted = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hosted)


class HostedForwardTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name) / "consumer"
    self.root.mkdir()
    self.git("init", "-q")
    self.git("config", "user.name", "fixture")
    self.git("config", "user.email", "fixture@example.invalid")
    (self.root / "original.txt").write_text("source\n", encoding="utf-8")
    self.git("add", "original.txt")
    self.git("commit", "-qm", "source")
    self.source_sha = self.git("rev-parse", "HEAD").strip()
    self.branch = "CMD-1-issue-788-fixture"
    self.git("switch", "-qc", self.branch)
    self.words = ["test", "RED", "--remote", "0"]
    self.commit_marker()
    self.event_path = Path(self.temp.name) / "event.json"
    self.environment = {
      "GITHUB_EVENT_NAME": "push",
      "GITHUB_REF": "refs/heads/" + self.branch,
      "GITHUB_SHA": self.git("rev-parse", "HEAD").strip(),
      "GITHUB_REPOSITORY": "example/fixture",
      "GITHUB_WORKFLOW_REF": (
        "example/fixture/.github/workflows/remote-rwf.yml@"
        + "refs/heads/" + self.branch
      ),
      "GITHUB_EVENT_PATH": str(self.event_path),
    }
    self.write_event()

  def git(self, *args):
    completed = subprocess.run(
      ["git", *args], cwd=self.root, capture_output=True, check=False,
    )
    self.assertEqual(
      completed.returncode, 0,
      completed.stderr.decode("utf-8", errors="replace"),
    )
    return completed.stdout.decode("utf-8", errors="strict")

  def commit_marker(self, words=None, extra=False, raw=None):
    marker = self.root / ".ci" / "rwf"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(
      (shlex.join(self.words if words is None else words) + "\n")
      if raw is None else raw,
      encoding="utf-8", newline="\n",
    )
    self.git("add", ".ci/rwf")
    if extra:
      (self.root / "unauthorized").write_text("bad\n", encoding="utf-8")
      self.git("add", "unauthorized")
    self.git("commit", "-qm", "CMD request")

  def write_event(self, **changes):
    event = {
      "ref": self.environment["GITHUB_REF"],
      "after": self.environment["GITHUB_SHA"],
      "deleted": False,
      "forced": False,
      "repository": {"full_name": "example/fixture"},
    }
    event.update(changes)
    self.event_path.write_text(json.dumps(event), encoding="utf-8")

  def check_failure(self, expected):
    with self.assertRaisesRegex(hosted.HostedForwardError, expected):
      hosted.authenticated_argv(self.root, self.environment)

  def test_literal_argv_roundtrip(self):
    self.assertEqual(
      hosted.authenticated_argv(self.root, self.environment),
      (self.branch, self.words),
    )

  def test_quotes_unicode_and_shell_metacharacters_remain_data(self):
    self.words = ["test", "RED", "a b", "Ω'$(touch a)", "", "--remote", "0"]
    self.commit_marker()
    self.environment["GITHUB_SHA"] = self.git("rev-parse", "HEAD").strip()
    self.write_event()
    self.assertEqual(hosted.authenticated_argv(self.root, self.environment)[1], self.words)

  def test_reject_non_push_event(self):
    self.environment["GITHUB_EVENT_NAME"] = "workflow_dispatch"
    self.check_failure("push event")

  def test_reject_non_cmd_branch(self):
    self.environment["GITHUB_REF"] = "refs/heads/main"
    self.check_failure("numbered CMD")

  def test_reject_wrong_workflow(self):
    self.environment["GITHUB_WORKFLOW_REF"] = "example/fixture/.github/workflows/ci.yml@refs/heads/" + self.branch
    self.check_failure("wrong hosted forwarding workflow")

  def test_reject_provider_sha_mismatch(self):
    self.environment["GITHUB_SHA"] = "a" * 40
    self.write_event()
    self.check_failure("checkout does not match")

  def test_reject_wrong_repository(self):
    self.write_event(repository={"full_name": "another/fixture"})
    self.check_failure("repository mismatch")

  def test_reject_force_push(self):
    self.write_event(forced=True)
    self.check_failure("provider event does not match")

  def test_reject_missing_retry_count(self):
    self.commit_marker(["test", "RED", "--remote"])
    self.environment["GITHUB_SHA"] = self.git("rev-parse", "HEAD").strip()
    self.write_event()
    self.check_failure("numbered --remote")

  def test_reject_unbalanced_quotes(self):
    self.commit_marker(raw="test RED 'unterminated --remote 0\n")
    self.environment["GITHUB_SHA"] = self.git("rev-parse", "HEAD").strip()
    self.write_event()
    self.check_failure("invalid committed argv")

  def test_reject_extra_changed_paths(self):
    self.commit_marker(extra=True)
    self.environment["GITHUB_SHA"] = self.git("rev-parse", "HEAD").strip()
    self.write_event()
    self.check_failure("modify only")

  def test_reject_no_marker_change(self):
    (self.root / "other").write_text("bad", encoding="utf-8")
    self.git("add", "other")
    self.git("commit", "-qm", "not request")
    self.environment["GITHUB_SHA"] = self.git("rev-parse", "HEAD").strip()
    self.write_event()
    self.check_failure("modify only")

  def test_workflow_filter_is_only_cmd_marker(self):
    workflow = (ROOT / ".github/workflows/remote-rwf.yml").read_text(encoding="utf-8")
    self.assertIn("- 'CMD-*'", workflow)
    self.assertIn("- '.ci/rwf'", workflow)
    self.assertNotIn("- '.ci/run'", workflow)
    self.assertIn("fetch-depth: 0", workflow)
    self.assertIn('python "$RWF_ENGINE_ROOT/scripts/hosted-rwf-forward.py"', workflow)
    self.assertEqual(workflow.count("  forward:"), 1)


if __name__ == "__main__":
  unittest.main()
