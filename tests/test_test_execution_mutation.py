"""Verify that a test mutating Git history cannot create reusable PASS."""
import json
import unittest

from tests import test_test_cli as fixture


class ExecutionMutationTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def test_clean_test_that_commits_during_run_is_nonreusable(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-mutation",
    )
    source = self.root / "smoke_case.py"
    source.write_text(
      "import subprocess\n"
      "import unittest\n"
      "from pathlib import Path\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_commit(self):\n"
      "    Path('generated.txt').write_text('changed\\n')\n"
      "    subprocess.run(['git','add','generated.txt'],check=True)\n"
      "    subprocess.run(['git','commit','-qm','generated'],check=True)\n"
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture mutation")
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-545-mutation\n")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "select test group")
    tested_sha = self.git("rev-parse", "HEAD")
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertNotEqual(self.git("rev-parse", "HEAD"), tested_sha)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(record["testSHA"], tested_sha)
    self.assertEqual(record["result"], "succeeded")
    self.assertEqual(record["uncommittedChanges"], [])
    self.assertTrue(record["headChangedDuringTest"])
    self.assertFalse(record["reusable"])


if __name__ == "__main__":
  unittest.main()
