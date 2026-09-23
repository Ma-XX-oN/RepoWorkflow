from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.config import load_config
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


if __name__ == "__main__":
  unittest.main()
