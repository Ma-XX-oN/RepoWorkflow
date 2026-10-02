from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.guard import GuardError, validate_stable_candidate
from repo_workflow.prelim import merge_accepted, start_prelim
from repo_workflow.results import finalize_stable_results
from repo_workflow.server_policy import (
  IntegrationAdmission,
  check_integration_admission,
)
from repo_workflow.version_adapter import run_transition
from tests.support import RepoFixture


class LifecycleIntegrationTests(unittest.TestCase):
  def test_guid_prelim_admission_land_and_stable_finalize(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      (root / "feature.txt").write_text("accepted\n", encoding="utf-8")
      fx.commit("accepted task")
      fx.push()
      config = load_config(root)

      started = start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      run_transition(root, config, "integrate", "--increment", "patch")
      candidate = fx.commit("prepare stable candidate")
      self.assertEqual((root / "VERSION").read_text().strip(), "1.0.1")

      admission = IntegrationAdmission(
        source_branch=started.branch,
        base_branch="main",
        candidate_sha=candidate,
        validation_sha=candidate,
        validation_passed=True,
        integration_authorized=True,
      )
      check_integration_admission(root, admission)

      with self.assertRaisesRegex(GuardError, "integration branch head"):
        validate_stable_candidate(root, expected_sha=candidate)

      fx._run("push", "origin", f"{candidate}:main")
      stable = validate_stable_candidate(root, expected_sha=candidate)
      self.assertEqual(stable.version, "1.0.1")
      self.assertEqual(stable.commit, candidate)

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
      outcome = finalize_stable_results(
        root,
        results,
        do_tag=True,
        push=True,
        expected_sha=candidate,
      )
      self.assertEqual(outcome, "PASS")
      peeled = fx._run(
        "ls-remote",
        "--tags",
        "origin",
        "refs/tags/v1.0.1^{}",
      ).stdout.strip()
      self.assertTrue(peeled)
      self.assertEqual(peeled.split()[0], candidate)


if __name__ == "__main__":
  unittest.main()
