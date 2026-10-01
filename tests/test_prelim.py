from pathlib import Path
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.prelim import (
  PRELIM_BRANCH,
  PrelimError,
  create_prelim_tag,
  merge_accepted,
  prelim_status,
  reintegrate_prelim,
  retire_prelim,
  start_prelim,
)
from repo_workflow.validation_audit import ValidationRecord, regression_reuse_decision
from tests.support import RepoFixture


class PrelimTests(unittest.TestCase):
  def make_diverged_fixture(self, root: Path) -> RepoFixture:
    fx = RepoFixture(root)
    (root / "feature.txt").write_text("accepted work\n", encoding="utf-8")
    fx.commit("accepted issue work")
    fx.push()
    return fx

  def test_start_and_merge_never_advance_local_main(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      main_before = fx._run("rev-parse", "main").stdout.strip()

      started = start_prelim(root, config)
      self.assertEqual(started, main_before)
      self.assertEqual(fx._run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), PRELIM_BRANCH)
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), main_before)

      candidate = merge_accepted(root, "issue-1-test")
      self.assertNotEqual(candidate, started)
      self.assertTrue((root / "feature.txt").exists())
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), main_before)
      self.assertTrue(prelim_status(root, config).current)

  def test_server_main_movement_requires_fresh_reintegration_and_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      start_prelim(root, config)
      old_candidate = merge_accepted(root, "issue-1-test")

      record = ValidationRecord(
        timestamp="2026-10-01T12:00:00Z",
        kind="regression",
        baseVersion="1.0.0",
        branch=PRELIM_BRANCH,
        testVersion="1.0.0-issue.1.0.1",
        testSHA=old_candidate,
        candidateTag=None,
        result="succeeded",
        runner="local",
      )
      self.assertEqual(regression_reuse_decision([record], old_candidate), "reuse-pass")

      fx._run("switch", "-c", "server-advance", "main")
      (root / "server.txt").write_text("new server main\n", encoding="utf-8")
      fx.commit("server main advance")
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", PRELIM_BRANCH)

      stale = prelim_status(root, config)
      self.assertFalse(stale.current)
      new_candidate = reintegrate_prelim(root, config)
      self.assertNotEqual(new_candidate, old_candidate)
      self.assertTrue((root / "feature.txt").exists())
      self.assertTrue((root / "server.txt").exists())
      self.assertTrue(prelim_status(root, config).current)
      self.assertEqual(regression_reuse_decision([record], new_candidate), "run")

  def test_prelim_tag_is_immutable_and_keeps_candidate_reachable(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      (root / "VERSION").write_text("1.0.1\n", encoding="utf-8")
      fx.commit("prepare stable prelim version")
      candidate = fx.head()

      tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=1,
        push=True,
      )
      self.assertEqual(tag, "v1.0.1-PRELIM-1.0.1")
      target = fx._run("rev-parse", f"{tag}^{{}}").stdout.strip()
      self.assertEqual(target, candidate)
      with self.assertRaises(PrelimError):
        create_prelim_tag(
          root,
          config,
          issue=1,
          integration_generation=0,
          validation_iteration=1,
        )

      fx._run("switch", "main")
      fx._run("branch", "-D", PRELIM_BRANCH)
      self.assertEqual(fx._run("rev-parse", f"{tag}^{{}}").stdout.strip(), candidate)

  def test_retire_requires_landed_candidate_and_resyncs_local_main(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      start_prelim(root, config)
      candidate = merge_accepted(root, "issue-1-test")

      with self.assertRaises(PrelimError):
        retire_prelim(root, config)

      fx._run("push", "origin", f"{candidate}:main")
      landed = retire_prelim(root, config)
      self.assertEqual(landed, candidate)
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), candidate)
      self.assertNotEqual(
        fx._run("show-ref", "--verify", "refs/heads/prelim-main", check=False).returncode,
        0,
      )

      start = start_prelim(root, config)
      self.assertEqual(start, candidate)


if __name__ == "__main__":
  unittest.main()
