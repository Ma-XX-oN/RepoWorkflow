from pathlib import Path
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.guard import GuardError, validate_candidate
from tests.support import RepoFixture


class GuardIntegrationBranchTests(unittest.TestCase):
  def test_development_candidate_on_integration_branch_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      fixture = RepoFixture(Path(directory) / "repo")
      fixture._run("checkout", "main")
      config = load_config(fixture.root)

      with self.assertRaisesRegex(
        GuardError,
        r"development candidate cannot run on integration branch main",
      ):
        validate_candidate(fixture.root, config)

  def test_development_candidate_on_issue_branch_is_accepted(self):
    with tempfile.TemporaryDirectory() as directory:
      fixture = RepoFixture(Path(directory) / "repo")
      config = load_config(fixture.root)

      candidate = validate_candidate(fixture.root, config)

      self.assertEqual(candidate.version, "1.0.0-issue.1.1")
      self.assertEqual(candidate.commit, fixture.head())
      self.assertEqual(candidate.remote, "origin")


if __name__ == "__main__":
  unittest.main()
