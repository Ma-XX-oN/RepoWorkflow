from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.guard import validate_stable_candidate
from repo_workflow.prelim import (
  create_prelim_tag,
  merge_accepted,
  retire_prelim,
  start_prelim,
)
from repo_workflow.results import finalize_stable_results
from repo_workflow.validation_audit import (
  ValidationRecord,
  regression_reuse_decision,
)
from repo_workflow.version_adapter import run_transition
from tests.support import RepoFixture


def _record(
  *,
  sha: str,
  result: str,
  version: str = "1.0.0-issue.1.0.1",
  kind: str = "regression",
  tag: str | None = None,
) -> ValidationRecord:
  return ValidationRecord(
    timestamp="2026-10-02T12:00:00Z",
    kind=kind,
    baseVersion="1.0.0",
    branch="issue-1-test",
    testVersion=version,
    testSHA=sha,
    candidateTag=tag,
    result=result,
    runner="local",
  )


class ConsumerPilotTests(unittest.TestCase):
  def test_happy_path_lands_cleans_prelim_and_finalizes_stable_tag(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      (root / "feature.txt").write_text("accepted\n", encoding="utf-8")
      accepted = fx.commit("accepted task")
      fx.push()
      config = load_config(root)

      started = start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      run_transition(root, config, "integrate", "--increment", "patch")
      candidate = fx.commit("prepare integrated stable candidate")
      prelim_tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=1,
        push=True,
      )

      self.assertNotEqual(candidate, accepted)
      self.assertEqual((root / "VERSION").read_text().strip(), "1.0.1")
      self.assertEqual(
        fx._run("rev-parse", f"{prelim_tag}^{{}}").stdout.strip(),
        candidate,
      )

      fx._run("push", "origin", started.branch)
      fx._run("push", "origin", f"{candidate}:main")
      landed = retire_prelim(root, config, started.branch)

      self.assertEqual(landed, candidate)
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), candidate)
      self.assertNotIn(
        f"refs/heads/{started.branch}",
        fx._run("ls-remote", "--heads", "origin").stdout,
      )
      self.assertEqual(
        fx._run("rev-parse", f"{prelim_tag}^{{}}").stdout.strip(),
        candidate,
      )

      stable = validate_stable_candidate(root, expected_sha=candidate)
      self.assertEqual(stable.version, "1.0.1")
      results = root.parent / "stable-results"
      results.mkdir()
      (results / "local.json").write_text(
        json.dumps({
          "schema": 1,
          "environment": "local",
          "required": True,
          "version": "1.0.1",
          "commit": candidate,
          "status": "PASS",
        }),
        encoding="utf-8",
      )
      self.assertEqual(
        finalize_stable_results(
          root,
          results,
          do_tag=True,
          push=True,
          expected_sha=candidate,
        ),
        "PASS",
      )
      remote_tags = fx._run("ls-remote", "--tags", "origin").stdout
      self.assertIn("refs/tags/v1.0.1", remote_tags)
      self.assertIn(f"refs/tags/{prelim_tag}", remote_tags)

  def test_regression_failure_recovery_keeps_failed_candidate_reachable(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      failed_sha = fx.head()
      failed_tag = "v1.0.0-issue.1.0.1-CI-FAIL"
      fx._run("tag", "-a", failed_tag, failed_sha, "-m", failed_tag)
      record = _record(
        sha=failed_sha,
        result="failed",
        tag=failed_tag,
      )

      run_transition(
        root,
        load_config(root),
        "task",
        "--increment",
        "CI-iteration",
      )
      fx.commit("advance regression iteration")
      (root / "fix.txt").write_text("fixed\n", encoding="utf-8")
      replacement = fx.commit("fix regression")

      self.assertEqual(
        (root / "VERSION").read_text().strip(),
        "1.0.0-issue.1.0.2",
      )
      self.assertEqual(
        fx._run("rev-parse", f"{failed_tag}^{{}}").stdout.strip(),
        failed_sha,
      )
      self.assertEqual(
        regression_reuse_decision([record], failed_sha),
        "reuse-terminal",
      )
      self.assertEqual(regression_reuse_decision([record], replacement), "run")

  def test_integration_failure_recovery_advances_q_resets_r_and_isolates_evidence(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      failed_sha = fx.head()
      failed = _record(
        sha=failed_sha,
        result="failed",
        version="1.0.0-issue.1.3.7",
        kind="integration",
      )

      run_transition(
        root,
        load_config(root),
        "task",
        "--increment",
        "merge-integration-failed",
      )
      fx.commit("advance integration generation")
      (root / "fix.txt").write_text("integration fixed\n", encoding="utf-8")
      replacement = fx.commit("fix integration")

      self.assertEqual(
        (root / "VERSION").read_text().strip(),
        "1.0.0-issue.1.4.1",
      )
      self.assertNotEqual(replacement, failed_sha)
      self.assertEqual(failed.testSHA, failed_sha)

  def test_incomplete_candidate_may_retry_but_cannot_validate_changed_candidate(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      candidate = fx.head()
      incomplete = _record(sha=candidate, result="incomplete")

      self.assertEqual(
        regression_reuse_decision([incomplete], candidate),
        "run",
      )

      (root / "changed.txt").write_text("changed\n", encoding="utf-8")
      changed = fx.commit("change candidate")
      self.assertNotEqual(changed, candidate)
      self.assertEqual(regression_reuse_decision([incomplete], changed), "run")


if __name__ == "__main__":
  unittest.main()
