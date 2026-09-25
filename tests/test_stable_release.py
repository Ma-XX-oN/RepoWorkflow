from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.guard import GuardError, validate_stable_candidate
from repo_workflow.results import finalize_stable_results
from tests.support import RepoFixture


class StableReleaseTests(unittest.TestCase):
  def make(self, version: str = "1.2.3"):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    fixture = RepoFixture(root, version=version)
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

  def test_stable_candidate_requires_plain_semver_and_exact_integration_head(self):
    td, root, fx = self.make()
    with td:
      candidate = validate_stable_candidate(root, expected_sha=fx.head())
      self.assertEqual(candidate.version, "1.2.3")
      self.assertEqual(candidate.commit, fx.head())

  def test_development_version_is_not_a_stable_candidate(self):
    td, root, fx = self.make("1.2.3-issue.9.4")
    with td:
      with self.assertRaisesRegex(GuardError, "stable version"):
        validate_stable_candidate(root)

  def test_unpublished_integration_head_is_not_a_stable_candidate(self):
    td, root, fx = self.make()
    with td:
      (root / "new.txt").write_text("new\n", encoding="utf-8")
      fx.commit("new candidate")
      with self.assertRaisesRegex(GuardError, "integration branch"):
        validate_stable_candidate(root)

  def test_existing_stable_tag_is_immutable(self):
    td, root, fx = self.make()
    with td:
      fx.tag_remote("v1.2.3")
      with self.assertRaisesRegex(GuardError, "stable release tag"):
        validate_stable_candidate(root)

  def test_pass_can_create_and_push_stable_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "PASS")
      outcome = finalize_stable_results(root, results, do_tag=True, push=True)
      self.assertEqual(outcome, "PASS")
      remote = fx._run("ls-remote", "--tags", "origin", "refs/tags/v1.2.3").stdout
      self.assertIn("refs/tags/v1.2.3", remote)

  def test_failure_never_creates_a_stable_tag(self):
    td, root, fx = self.make()
    with td:
      results = root.parent / "results"
      self.write_result(results, fx, "FAIL")
      outcome = finalize_stable_results(root, results, do_tag=True, push=True)
      self.assertEqual(outcome, "FAIL")
      self.assertEqual(fx._run("tag", "--list", "v1.2.3").stdout.strip(), "")


if __name__ == "__main__":
  unittest.main()
