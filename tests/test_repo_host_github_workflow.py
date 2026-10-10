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
      "runs-on: [self-hosted, linux, rwf97-trusted]",
      "secrets.RWF97_SANDBOX_GH_TOKEN",
      "vars.RWF97_SANDBOX_REPOSITORY",
      "vars.RWF97_AUTH_EXECUTABLE",
      "vars.RWF97_AUTH_SHA256",
      'test "$SANDBOX_REPOSITORY" != "Ma-XX-oN/RepoWorkflow"',
      "scripts/probe-repo-host-github.py",
    ):
      self.assertIn(required, source)

  def test_native_read_audit_and_sandbox_token_separation(self):
    source = LIVE.read_text(encoding="utf-8")
    self.assertIn("actions: read", source)
    self.assertIn("GH_TOKEN: ${{ github.token }}", source)
    self.assertIn(
      "GH_TOKEN: ${{ secrets.RWF97_SANDBOX_GH_TOKEN }}",
      source,
    )
    self.assertIn("vars.RWF97_APPROVED_SHA == github.sha", source)

  def test_sandbox_hosted_native_token_needs_no_custom_runner_or_app(self):
    path = ROOT / "examples/issue-97-sandbox-hosted.workflow.yml"
    source = path.read_text(encoding="utf-8")
    for expected in (
      "on:\n  workflow_dispatch:",
      "runs-on: ubuntu-latest",
      "vars.RWF97_TRUSTED_MAIN_SHA == github.sha",
      "vars.RWF97_APPROVED_GRANT_ID",
      "vars.RWF97_SIGNED_REVOCATIONS",
      "vars.RWF97_ISSUER_PUBLIC_KEY",
      "vars.RWF97_ISSUER_AUTHORITY",
      "actions: read",
      "contents: write",
      "issues: write",
      "pull-requests: write",
      "GH_TOKEN: ${{ github.token }}",
      "github.repository != 'Ma-XX-oN/RepoWorkflow'",
      "github.ref == 'refs/heads/main'",
      "RWF97_APPROVED_SHA",
      "RWF97_VERIFIER_SHA256",
      "inputs.mode == 'accept'",
      "inputs.mode == 'deny'",
      "probe-repo-host-github-private-sandbox-signed-deny.py",
      "sha256sum --check --status",
      "git -C \"$RUNNER_TEMP/rwf97-candidate\" rev-parse HEAD",
      "scripts/probe-repo-host-github.py",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    for forbidden in (
      "pull_request_target:", "  pull_request:",
      "self-hosted", "APP_PRIVATE_KEY", "RWF97_SANDBOX_GH_TOKEN",
      "actions/create-github-app-token", "secrets.",
      "--repository Ma-XX-oN/RepoWorkflow",
    ):
      self.assertNotIn(forbidden, source)

  def test_sandbox_environment_verifier_denies_invalid_policy(self):
    path = ROOT / "examples/issue-97-sandbox-verify-environment.py"
    spec = importlib.util.spec_from_file_location(
      "issue97_sandbox_environment", path
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    good = {
      "name": "rwf97-acceptance",
      "protection_rules": [{
        "type": "required_reviewers", "prevent_self_review": True,
        "reviewers": [{"type": "User"}],
      }],
      "deployment_branch_policy": {"custom_branch_policies": True},
    }
    branches = {
      "total_count": 1,
      "branch_policies": [{"name": "main"}],
    }
    helper.check_policy(good, branches, "owner/disposable", "main")
    cases = [
      ({**good, "name": "production"}, branches, "owner/disposable"),
      ({**good, "protection_rules": []}, branches, "owner/disposable"),
      ({**good, "protection_rules": [{
        "type": "required_reviewers", "prevent_self_review": False,
        "reviewers": [{"type": "User"}],
      }]}, branches, "owner/disposable"),
      ({**good, "deployment_branch_policy": {}}, branches,
       "owner/disposable"),
      (good, {"total_count": 1, "branch_policies": [{"name": "*"}]},
       "owner/disposable"),
      (good, branches, "Ma-XX-oN/RepoWorkflow"),
    ]
    for environment, policy, repo in cases:
      with self.subTest(environment=environment, policy=policy, repo=repo):
        with self.assertRaises(RuntimeError):
          helper.check_policy(environment, policy, repo, "main")

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
