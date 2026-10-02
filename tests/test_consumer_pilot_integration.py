from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.guard import validate_stable_candidate
from repo_workflow.prelim import (
  create_prelim_tag,
  merge_accepted,
  prelim_status,
  reintegrate_prelim,
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


class ConsumerPilotIntegrationTests(unittest.TestCase):
  def _accepted_fixture(self, root: Path) -> RepoFixture:
    fx = RepoFixture(root)
    (root / "feature.txt").write_text("accepted\n", encoding="utf-8")
    fx.commit("accepted task")
    fx.push()
    return fx

  def _clone_worker(
    self,
    source: RepoFixture,
    root: Path,
  ) -> RepoFixture:
    subprocess.run(
      [
        "git",
        "clone",
        "--branch",
        "issue-1-test",
        str(source.remote),
        str(root),
      ],
      check=True,
      capture_output=True,
      text=True,
    )
    worker = object.__new__(RepoFixture)
    worker.root = root
    worker.remote = source.remote
    worker.version = source.version
    worker._run("config", "user.name", "Worker")
    worker._run("config", "user.email", "worker@example.invalid")
    return worker

  def test_main_advance_forces_fresh_prelim_identity_and_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self._accepted_fixture(root)
      config = load_config(root)

      started = start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      run_transition(root, config, "integrate", "--increment", "patch")
      first_candidate = fx.commit("prepare first stable candidate")
      first_tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=1,
      )
      first_record = ValidationRecord(
        timestamp="2026-10-02T13:00:00Z",
        kind="regression",
        baseVersion="1.0.0",
        branch=started.branch,
        testVersion="1.0.1",
        testSHA=first_candidate,
        candidateTag=first_tag,
        result="succeeded",
        runner="local",
      )
      first_record.validate()
      self.assertEqual(first_record.issue, 1)
      self.assertEqual(
        regression_reuse_decision([first_record], first_candidate),
        "reuse-pass",
      )

      fx._run("switch", "-c", "server-advance", "main")
      (root / "server.txt").write_text("server advanced\n", encoding="utf-8")
      fx.commit("advance server main")
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", started.branch)

      self.assertFalse(prelim_status(root, config, started.branch).current)
      second_candidate = reintegrate_prelim(root, config, started.branch)
      self.assertNotEqual(second_candidate, first_candidate)
      self.assertEqual(
        regression_reuse_decision([first_record], second_candidate),
        "run",
      )
      second_tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=2,
      )
      self.assertNotEqual(second_tag, first_tag)
      self.assertEqual(
        fx._run("rev-parse", f"{first_tag}^{{}}").stdout.strip(),
        first_candidate,
      )
      self.assertEqual(
        fx._run("rev-parse", f"{second_tag}^{{}}").stdout.strip(),
        second_candidate,
      )

  def test_two_workers_land_sequentially_without_cross_cleanup(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      first_root = base / "first"
      first_root.mkdir()
      first = self._accepted_fixture(first_root)
      second_root = base / "second"
      second = self._clone_worker(first, second_root)

      first_config = load_config(first_root)
      second_config = load_config(second_root)
      first_started = start_prelim(first_root, first_config)
      first_candidate = merge_accepted(first_root, "issue-1-test")
      second_started = start_prelim(second_root, second_config)
      second_candidate = merge_accepted(second_root, "issue-1-test")

      first._run("push", "origin", first_started.branch)
      second._run("push", "origin", second_started.branch)
      first._run("push", "origin", f"{first_candidate}:main")
      retire_prelim(first_root, first_config, first_started.branch)

      remote = first._run("ls-remote", "--heads", "origin").stdout
      self.assertNotIn(f"refs/heads/{first_started.branch}", remote)
      self.assertIn(f"refs/heads/{second_started.branch}", remote)

      self.assertFalse(
        prelim_status(second_root, second_config, second_started.branch).current
      )
      refreshed = reintegrate_prelim(
        second_root,
        second_config,
        second_started.branch,
      )
      self.assertNotEqual(refreshed, second_candidate)
      second._run("push", "origin", second_started.branch)
      second._run("push", "origin", f"{refreshed}:main")
      retire_prelim(second_root, second_config, second_started.branch)

      final_remote = second._run("ls-remote", "--heads", "origin").stdout
      self.assertNotIn(f"refs/heads/{first_started.branch}", final_remote)
      self.assertNotIn(f"refs/heads/{second_started.branch}", final_remote)

  def test_squash_landing_keeps_prelim_tag_and_stable_tag_targets_landed_sha(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self._accepted_fixture(root)
      config = load_config(root)

      started = start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      run_transition(root, config, "integrate", "--increment", "patch")
      candidate = fx.commit("prepare squash candidate")
      prelim_tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=1,
        push=True,
      )
      record = ValidationRecord(
        timestamp="2026-10-02T13:30:00Z",
        kind="regression",
        baseVersion="1.0.0",
        branch=started.branch,
        testVersion="1.0.1",
        testSHA=candidate,
        candidateTag=prelim_tag,
        result="succeeded",
        runner="local",
      )
      record.validate()
      self.assertEqual(record.issue, 1)
      fx._run("push", "origin", started.branch)

      fx._run("switch", "main")
      fx._run("checkout", candidate, "--", ".")
      squash = fx.commit("squash integrated release")
      self.assertNotEqual(squash, candidate)
      self.assertEqual(
        fx._run(
          "diff",
          "--quiet",
          squash,
          candidate,
          "--",
          check=False,
        ).returncode,
        0,
      )
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", started.branch)
      landed = retire_prelim(root, config, started.branch)
      self.assertEqual(landed, squash)

      stable = validate_stable_candidate(root, expected_sha=squash)
      self.assertEqual(stable.version, "1.0.1")
      results = root.parent / "stable-results"
      results.mkdir()
      (results / "local.json").write_text(
        json.dumps({
          "schema": 1,
          "environment": "local",
          "required": True,
          "version": "1.0.1",
          "commit": squash,
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
          expected_sha=squash,
        ),
        "PASS",
      )

      self.assertEqual(
        fx._run("rev-parse", f"{prelim_tag}^{{}}").stdout.strip(),
        candidate,
      )
      self.assertEqual(
        fx._run("rev-parse", "v1.0.1^{}").stdout.strip(),
        squash,
      )


if __name__ == "__main__":
  unittest.main()
