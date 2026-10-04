from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from repo_workflow.config import load_config
from repo_workflow.git import git as real_git
from repo_workflow.results import ResultError, finalize_results
from tests.support import RepoFixture


class FinalizeTests(unittest.TestCase):
  def make(self):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    fixture = RepoFixture(root)
    return td, root, fixture

  def write_result(self, directory: Path, fx: RepoFixture, status: str):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "local.json").write_text(json.dumps({
      "schema": 1,
      "environment": "local",
      "required": True,
      "version": fx.version,
      "commit": fx.head(),
      "status": status,
    }))

  def test_pass_can_create_and_push_terminal_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "PASS")
      outcome = finalize_results(root, results, do_tag=True, push=True)
      self.assertEqual(outcome, "PASS")
      remote = fx._run("ls-remote", "--tags", "origin", f"refs/tags/v{fx.version}").stdout
      self.assertIn(f"refs/tags/v{fx.version}", remote)

  def test_failure_can_create_ci_fail_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "FAIL")
      outcome = finalize_results(root, results, do_tag=True, push=False)
      self.assertEqual(outcome, "FAIL")
      tag = fx._run("tag", "--list", f"v{fx.version}-CI-FAIL").stdout.strip()
      self.assertEqual(tag, f"v{fx.version}-CI-FAIL")

  def test_incomplete_does_not_create_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "INCOMPLETE")
      outcome = finalize_results(root, results, do_tag=True, push=False)
      self.assertEqual(outcome, "INCOMPLETE")
      self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")

  def test_push_without_tag_is_rejected(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "PASS")
      with self.assertRaises(ResultError):
        finalize_results(root, results, do_tag=False, push=True)


  def test_terminal_collision_detected_again_at_finalization_boundary(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "PASS")

      def injected_git(repo, *args, **kwargs):
        if args[:2] == ("ls-remote", "--tags"):
          return SimpleNamespace(
            returncode=0,
            stdout=(
              "deadbeef"
              + chr(9)
              + f"refs/tags/v{fx.version}-CI-FAIL"
              + chr(10)
            ),
            stderr="",
          )
        return real_git(repo, *args, **kwargs)

      with patch("repo_workflow.results.git", side_effect=injected_git):
        with self.assertRaisesRegex(ResultError, "immutable terminal result"):
          finalize_results(root, results, do_tag=True, push=False)
      self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")

  def test_failed_terminal_tag_push_rolls_back_local_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "PASS")

      def injected_git(repo, *args, **kwargs):
        if args[:2] == ("push", "origin") and args[2].startswith("refs/tags/"):
          return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="injected terminal-tag push failure",
          )
        return real_git(repo, *args, **kwargs)

      with patch("repo_workflow.results.git", side_effect=injected_git):
        with self.assertRaisesRegex(ResultError, "failed to publish"):
          finalize_results(root, results, do_tag=True, push=True)
      self.assertEqual(fx._run("tag", "--list").stdout.strip(), "")



if __name__ == "__main__":
  unittest.main()
