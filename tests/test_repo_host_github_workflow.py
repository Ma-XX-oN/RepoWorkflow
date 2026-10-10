"""Specification guards for #97's protected, opt-in live test lane."""
from __future__ import annotations

from pathlib import Path
import unittest
import importlib.util


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
      "vars.RWF97_APPROVED_SHA == github.sha",
      "git rev-parse HEAD",
      "environment: rwf97-sandbox",
      "runs-on: [self-hosted, rwf97-trusted]",
      "secrets.RWF97_SANDBOX_GH_TOKEN",
      "secrets.RWF97_CONFIG_AUDIT_GH_TOKEN",
      "vars.RWF97_SANDBOX_REPOSITORY",
      "vars.RWF97_AUTH_EXECUTABLE",
      'test "$SANDBOX_REPOSITORY" != "Ma-XX-oN/RepoWorkflow"',
      "scripts/probe-repo-host-github.py",
    ):
      self.assertIn(required, source)

  def test_audit_and_mutation_tokens_remain_distinct(self):
    source = LIVE.read_text(encoding="utf-8")
    self.assertIn(
      "GH_TOKEN: ${{ secrets.RWF97_CONFIG_AUDIT_GH_TOKEN }}",
      source,
    )
    self.assertIn(
      "GH_TOKEN: ${{ secrets.RWF97_SANDBOX_GH_TOKEN }}",
      source,
    )
    self.assertNotIn("GH_TOKEN: ${{ github.token }}", source)
    self.assertIn(
      "vars.RWF97_APPROVED_SHA == github.sha", source
    )

  def test_environment_policy_requires_independent_review(self):
    path = ROOT / "scripts/probe-repo-host-github-environment.py"
    spec = importlib.util.spec_from_file_location(
      "issue97_environment", path
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    valid = {
      "name": "rwf97-sandbox",
      "protection_rules": [{
        "type": "required_reviewers", "prevent_self_review": True,
        "reviewers": [{"type": "User", "reviewer": {"login": "owner"}}],
      }],
      "deployment_branch_policy": {
        "protected_branches": False, "custom_branch_policies": True,
      },
    }
    helper.validate_environment(valid)
    helper.validate_branch_policies({
      "total_count": 1,
      "branch_policies": [{
        "name": "issue-97-github-host-mutation-adapter",
      }],
    })
    for invalid in [
      {"total_count": 0, "branch_policies": []},
      {"total_count": 1, "branch_policies": [{"name": "*"}]},
      {"total_count": 1, "branch_policies": [{"name": "main"}]},
      {"total_count": 2, "branch_policies": [
        {"name": "issue-97-github-host-mutation-adapter"},
        {"name": "main"},
      ]},
    ]:
      with self.subTest(invalid=invalid):
        with self.assertRaises(RuntimeError):
          helper.validate_branch_policies(invalid)
    for bad in [
      {**valid, "name": "production"},
      {**valid, "protection_rules": []},
      {**valid, "protection_rules": [{
        "type": "required_reviewers", "prevent_self_review": False,
        "reviewers": [{"type": "User"}],
      }]},
      {**valid, "deployment_branch_policy": None},
    ]:
      with self.subTest(bad=bad):
        with self.assertRaises(RuntimeError):
          helper.validate_environment(bad)

  def test_configuration_inspection_is_read_only_and_conservative(self):
    path = ROOT / "scripts/probe-repo-host-github-configuration.py"
    spec = importlib.util.spec_from_file_location(
      "issue97_configuration", path
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    self.assertEqual(
      helper.inspection_status(1, "HTTP 403 forbidden"),
      "INSUFFICIENT_INSPECTION_PERMISSION",
    )
    self.assertEqual(
      helper.inspection_status(1, "HTTP 404 not found"),
      "NOT_FOUND_OR_CONCEALED",
    )
    self.assertEqual(
      helper.inspection_status(0, ""),
      "READABLE",
    )
    source = path.read_text(encoding="utf-8")
    self.assertIn('"--method", "GET"', source)
    self.assertNotIn('"--method", "POST"', source)
    self.assertNotIn('"--method", "PATCH"', source)

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
