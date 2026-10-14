"""Dedicated Git commits must exclude separately staged test evidence."""
import json
import unittest

from tests import test_test_cli as fixture


class DedicatedCommitTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  remote = fixture.TestCliContract.remote
  _catalogue = fixture.TestCliContract._catalogue

  def _stage_log(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"result": "incomplete"}) + "\n")
    self.git("add", "-f", "--", str(path.relative_to(self.root)))
    return path

  def test_staged_audit_is_not_in_red_selection_commit(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    path = self._stage_log()
    result = self.cli("test", "RED", "issue-545-one")
    self.assertEqual(result.returncode, 2, result.stderr)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
      ".ci/red-green.txt",
    )
    self.assertIn(
      str(path.relative_to(self.root)),
      self.git("diff", "--cached", "--name-only"),
    )

  def test_staged_audit_is_not_in_hosted_request_commit(self):
    server = self.remote()
    path = self._stage_log()
    before = self.git("rev-parse", "HEAD")
    result = self.cli("test", "regression", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
      ".ci/run",
    )
    self.assertEqual(self.git("rev-parse", "HEAD^"), before)
    self.assertIn(
      str(path.relative_to(self.root)),
      self.git("diff", "--cached", "--name-only"),
    )
    self.assertEqual(
      self.git("rev-parse", "HEAD"),
      __import__("subprocess").check_output(
        ["git", "--git-dir", str(server), "rev-parse",
         "refs/heads/issue-545-fixture"],
        text=True,
      ).strip(),
    )


if __name__ == "__main__":
  unittest.main()
