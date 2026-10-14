"""Protect the currently deployed, on-demand CI and release boundary."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "on-demand-ci.yml"


def job_block(text, name):
  match = re.search(r"(?m)^  " + re.escape(name) + r":\s*$", text)
  if match is None:
    raise AssertionError("missing hosted CI job: " + name)
  end = re.search(r"(?m)^  [a-z][a-z0-9-]*:\s*$", text[match.end():])
  return text[match.end():match.end() + end.start()] if end else text[match.end():]


def assert_safe_trigger(test, text):
  header = text.split("\npermissions:", 1)[0]
  test.assertRegex(header, r"(?m)^  push:\s*$")
  test.assertRegex(header, r"(?m)^      - ['\"]issue-\*['\"]\s*$")
  test.assertRegex(header, r"(?m)^      - ['\"]\.ci/run['\"]\s*$")
  test.assertNotRegex(header, r"(?m)^\s*(pull_request|workflow_dispatch):")
  test.assertNotRegex(header, r"(?m)^\s*- ['\"]main['\"]\s*$")


def assert_integration_probe(test, text, name):
  section = job_block(text, name)
  test.assertIn("needs.plan.outputs.stage == 'integration-testing'", section)
  for platform in ("ubuntu-latest", "windows-latest", "macos-latest"):
    test.assertIn(platform, section)
  test.assertIn("needs.plan.outputs.tested_sha", section)


class SelfCiTests(unittest.TestCase):
  def setUp(self):
    self.text = WORKFLOW.read_text(encoding="utf-8")

  def test_retired_self_ci_cannot_publish_stable_tags(self):
    self.assertFalse((WORKFLOW.parent / "self-ci.yml").exists())
    assert_safe_trigger(self, self.text)
    self.assertNotRegex(self.text, r"(?m)^  release:\s*$")
    self.assertNotIn("git tag -a", self.text)
    self.assertNotIn("refs/tags/", self.text)

  def test_hosted_invocation_is_narrow_and_cannot_run_on_main_push(self):
    assert_safe_trigger(self, self.text)
    self.assertIn("python scripts/on-demand-ci-plan.py", job_block(self.text, "plan"))
    self.assertIn("fetch-depth: 0", job_block(self.text, "plan"))

  def test_trigger_guard_rejects_main_and_pull_request_regressions(self):
    with self.assertRaises(AssertionError):
      assert_safe_trigger(self, self.text.replace("- 'issue-*'", "- main"))
    with self.assertRaises(AssertionError):
      assert_safe_trigger(
        self, self.text.replace("permissions:", "  pull_request:\npermissions:", 1)
      )

  def test_hosted_runner_executes_authoritative_regression_and_integration(self):
    section = job_block(self.text, "validate")
    for stage in ("RED", "temp", "GREEN", "regression", "integration"):
      self.assertIn(stage + "-testing", section)
    for command in ("RED", "temporary", "GREEN", "regression", "integration"):
      self.assertIn("./rwf test " + command, section)
    self.assertNotIn("scripts/validate.py", section)

  def test_hosted_execution_is_bound_to_verified_candidate(self):
    plan = job_block(self.text, "plan")
    self.assertIn("tested_sha", plan)
    for name in (
      "validate", "publish", "results", "argv-limits",
      "graph-renderer-platform", "ticket-merge-platform",
    ):
      self.assertIn(
        "ref: " + "$" + "{{ needs.plan.outputs.tested_sha }}",
        job_block(self.text, name),
        name,
      )

  def test_integration_probes_cover_all_three_platforms(self):
    for name in ("argv-limits", "graph-renderer-platform", "ticket-merge-platform"):
      assert_integration_probe(self, self.text, name)

  def test_regression_stage_does_not_trigger_platform_probes(self):
    for name in ("argv-limits", "graph-renderer-platform", "ticket-merge-platform"):
      section = job_block(self.text, name)
      self.assertNotIn("regression-testing", section)
      self.assertNotIn("GREEN-testing", section)

  def test_hosted_publisher_is_evidence_scoped_not_release_publisher(self):
    validate = job_block(self.text, "validate")
    publish = job_block(self.text, "publish")
    self.assertIn("actions/upload-artifact@v4", validate)
    self.assertIn("scripts/publish-hosted-result.py", publish)
    self.assertIn("actions/download-artifact@v4", publish)
    self.assertIn("contents: write", publish)
    self.assertNotIn("contents: write", validate)
    self.assertNotIn("git tag", publish)
    self.assertNotIn("refs/tags", publish)
    self.assertIn("steps.staged_evidence.outcome == 'success'", validate)

  def test_read_only_remote_results_are_preserved(self):
    results = job_block(self.text, "results")
    self.assertIn("./rwf test results --remote", results)
    self.assertIn("contents: read", results)
    self.assertNotIn("contents: write", results)
    self.assertIn("providerRunId", results)
    self.assertIn("providerInvocationSHA", results)

  def test_issue_validation_evidence_reports_resolved_groups(self):
    text = (ROOT / "scripts" / "validate-issue.py").read_text(encoding="utf-8")
    self.assertEqual(text.count('"groups": groups'), 2)
    self.assertNotIn('"groups": args.groups', text)


if __name__ == "__main__":
  unittest.main()
