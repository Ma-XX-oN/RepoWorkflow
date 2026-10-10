"""Specification guards for #97's protected, opt-in live test lane."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / ".github/workflows/issue-97-live-mutation.yml"
SAFE = ROOT / ".github/workflows/issue-97-platform-acceptance.yml"


class LiveAcceptanceWorkflowTests(unittest.TestCase):
  def test_no_untrusted_pr_trigger_or_native_write_token(self):
    source = LIVE.read_text(encoding="utf-8")
    self.assertNotIn("pull_request_target:", source)
    self.assertNotIn("  pull_request:", source)
    self.assertIn("permissions:\n  contents: read\n", source)
    for forbidden in (
      "write-all", "contents: write", "issues: write",
      "pull-requests: write",
    ):
      self.assertNotIn(forbidden, source)

  def test_separate_sandbox_and_user_opt_in_are_required(self):
    source = LIVE.read_text(encoding="utf-8")
    for required in (
      "vars.RWF97_ENABLE == 'true'",
      "environment: rwf97-sandbox",
      "runs-on: [self-hosted, rwf97-trusted]",
      "secrets.RWF97_SANDBOX_GH_TOKEN",
      "vars.RWF97_SANDBOX_REPOSITORY",
      "vars.RWF97_AUTH_EXECUTABLE",
      'test "$SANDBOX_REPOSITORY" != "Ma-XX-oN/RepoWorkflow"',
      "scripts/probe-repo-host-github.py",
    ):
      self.assertIn(required, source)

  def test_cross_platform_workflow_remains_read_only(self):
    source = SAFE.read_text(encoding="utf-8")
    self.assertIn("permissions:\n  contents: read\n", source)
    self.assertNotIn("contents: write", source)
    self.assertNotIn("issues: write", source)
    self.assertNotIn("pull-requests: write", source)
    self.assertIn("windows-latest", source)
    self.assertIn("macos-latest", source)
    self.assertIn("ubuntu-latest", source)


if __name__ == "__main__":
  unittest.main()
