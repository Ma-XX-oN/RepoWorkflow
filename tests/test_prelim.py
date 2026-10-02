from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.prelim import (
  PRELIM_PREFIX,
  PrelimError,
  create_prelim_tag,
  is_prelim_branch,
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

  def clone_worker(self, fx: RepoFixture, root: Path) -> RepoFixture:
    subprocess.run(
      ["git", "clone", "--branch", "issue-1-test", str(fx.remote), str(root)],
      check=True,
      capture_output=True,
      text=True,
    )
    worker = object.__new__(RepoFixture)
    worker.root = root
    worker.remote = fx.remote
    worker.version = fx.version
    worker._run("config", "user.name", "Worker")
    worker._run("config", "user.email", "worker@example.invalid")
    return worker

  def test_ordinary_issue_development_has_no_prelim_branch(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      branches = fx._run("branch", "--format=%(refname:short)").stdout.splitlines()
      self.assertFalse(any(name.startswith(PRELIM_PREFIX) for name in branches))
      self.assertNotIn("prelim-main", branches)

  def test_start_and_merge_use_unique_guid_branch_without_advancing_local_main(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      main_before = fx._run("rev-parse", "main").stdout.strip()
      issue_before = fx._run("rev-parse", "issue-1-test").stdout.strip()

      started = start_prelim(root, config)
      self.assertTrue(is_prelim_branch(started.branch))
      self.assertEqual(started.candidate, main_before)
      self.assertEqual(
        fx._run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
        started.branch,
      )
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), main_before)
      self.assertNotEqual(started.branch, "prelim-main")

      candidate = merge_accepted(root, "issue-1-test")
      self.assertNotEqual(candidate, started.candidate)
      self.assertTrue((root / "feature.txt").exists())
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), main_before)
      self.assertEqual(
        fx._run("rev-parse", "issue-1-test").stdout.strip(),
        issue_before,
      )
      self.assertTrue(prelim_status(root, config, started.branch).current)

  def test_two_workers_receive_distinct_branches_and_cannot_adopt_each_other(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      first_root = base / "first"
      first_root.mkdir()
      first = self.make_diverged_fixture(first_root)
      second_root = base / "second"
      second = self.clone_worker(first, second_root)

      first_status = start_prelim(first_root, load_config(first_root))
      second_status = start_prelim(second_root, load_config(second_root))
      self.assertNotEqual(first_status.attempt_id, second_status.attempt_id)
      self.assertNotEqual(first_status.branch, second_status.branch)

      first._run("push", "origin", first_status.branch)
      second._run("push", "origin", second_status.branch)
      remote = first._run("ls-remote", "--heads", "origin").stdout
      self.assertIn(f"refs/heads/{first_status.branch}", remote)
      self.assertIn(f"refs/heads/{second_status.branch}", remote)

      second._run("fetch", "origin", first_status.branch)
      second._run(
        "branch",
        first_status.branch,
        f"origin/{first_status.branch}",
      )
      second._run("switch", first_status.branch)
      with self.assertRaisesRegex(PrelimError, "not owned by this clone"):
        prelim_status(second_root, load_config(second_root), first_status.branch)

  def test_cleanup_one_attempt_preserves_concurrent_remote_attempt(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      first_root = base / "first"
      first_root.mkdir()
      first = self.make_diverged_fixture(first_root)
      second_root = base / "second"
      second = self.clone_worker(first, second_root)

      first_config = load_config(first_root)
      second_config = load_config(second_root)
      first_started = start_prelim(first_root, first_config)
      first_candidate = merge_accepted(first_root, "issue-1-test")
      second_started = start_prelim(second_root, second_config)

      first._run("push", "origin", first_started.branch)
      second._run("push", "origin", second_started.branch)
      first._run("push", "origin", f"{first_candidate}:main")

      retire_prelim(first_root, first_config, first_started.branch)

      remote = first._run("ls-remote", "--heads", "origin").stdout
      self.assertNotIn(f"refs/heads/{first_started.branch}", remote)
      self.assertIn(f"refs/heads/{second_started.branch}", remote)

  def test_squash_landing_allows_cleanup_and_keeps_prelim_tag_reachable(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      started = start_prelim(root, config)
      merge_accepted(root, "issue-1-test")
      (root / "VERSION").write_text("1.0.1\n", encoding="utf-8")
      candidate = fx.commit("stable prelim")
      tag = create_prelim_tag(
        root,
        config,
        issue=1,
        integration_generation=0,
        validation_iteration=1,
      )
      fx._run("push", "origin", started.branch)

      fx._run("switch", "main")
      fx._run("checkout", candidate, "--", ".")
      squash = fx.commit("squash landed candidate")
      self.assertNotEqual(squash, candidate)
      self.assertEqual(
        fx._run("diff", "--quiet", squash, candidate, "--", check=False).returncode,
        0,
      )
      fx._run("push", "origin", "HEAD:main")
      fx._run("switch", started.branch)

      landed = retire_prelim(root, config, started.branch)

      self.assertEqual(landed, squash)
      self.assertEqual(
        fx._run("rev-parse", f"{tag}^{{}}").stdout.strip(),
        candidate,
      )

  def test_server_main_movement_requires_fresh_reintegration_and_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      started = start_prelim(root, config)
      old_candidate = merge_accepted(root, "issue-1-test")

      record = ValidationRecord(
        timestamp="2026-10-01T12:00:00Z",
        kind="regression",
        baseVersion="1.0.0",
        branch=started.branch,
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
      fx._run("switch", started.branch)

      stale = prelim_status(root, config, started.branch)
      self.assertFalse(stale.current)
      new_candidate = reintegrate_prelim(root, config, started.branch)
      self.assertNotEqual(new_candidate, old_candidate)
      self.assertTrue((root / "feature.txt").exists())
      self.assertTrue((root / "server.txt").exists())
      self.assertTrue(prelim_status(root, config, started.branch).current)
      self.assertEqual(regression_reuse_decision([record], new_candidate), "run")

  def test_prelim_tag_is_immutable_and_keeps_candidate_reachable(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      started = start_prelim(root, config)
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
      fx._run("branch", "-D", started.branch)
      self.assertEqual(fx._run("rev-parse", f"{tag}^{{}}").stdout.strip(), candidate)

  def test_retire_requires_landed_candidate_and_deletes_only_its_refs(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = self.make_diverged_fixture(root)
      config = load_config(root)
      started = start_prelim(root, config)
      candidate = merge_accepted(root, "issue-1-test")
      fx._run("push", "origin", started.branch)

      with self.assertRaises(PrelimError):
        retire_prelim(root, config, started.branch)
      self.assertIn(
        f"refs/heads/{started.branch}",
        fx._run("ls-remote", "--heads", "origin").stdout,
      )

      fx._run("push", "origin", f"{candidate}:main")
      landed = retire_prelim(root, config, started.branch)
      self.assertEqual(landed, candidate)
      self.assertEqual(fx._run("rev-parse", "main").stdout.strip(), candidate)
      self.assertNotIn(
        f"refs/heads/{started.branch}",
        fx._run("ls-remote", "--heads", "origin").stdout,
      )
      self.assertNotEqual(
        fx._run(
          "show-ref",
          "--verify",
          f"refs/heads/{started.branch}",
          check=False,
        ).returncode,
        0,
      )

      later = start_prelim(root, config)
      self.assertEqual(later.candidate, candidate)
      self.assertNotEqual(later.attempt_id, started.attempt_id)


if __name__ == "__main__":
  unittest.main()
