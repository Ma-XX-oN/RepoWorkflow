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


  def test_red_that_commits_records_original_candidate_sha(self):
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
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-545-mutation\n")
    self.git("add", ".ci/tests.json", "smoke_case.py", ".ci/red-green.txt")
    self.git("commit", "-m", "select RED mutation fixture")
    tested_sha = self.git("rev-parse", "HEAD")
    result = self.cli("test", "RED")
    self.assertEqual(result.returncode, 2)
    self.assertNotEqual(self.git("rev-parse", "HEAD"), tested_sha)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(record["kind"], "RED")
    self.assertEqual(record["testSHA"], tested_sha)
    self.assertTrue(record["headChangedDuringTest"])
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])


  def test_regression_mutation_retains_original_candidate_and_invalidates_reuse(self):
    from unittest.mock import patch
    from repo_workflow.test_cli import run_test

    source = self.root / "generated.txt"
    candidate = self.git("rev-parse", "HEAD")

    def mutating_verify(*args, **kwargs):
      source.write_text("generated\\n")
      self.git("add", "generated.txt")
      self.git("commit", "-m", "mutation inside regression verifier")
      return "PASS"

    with patch("repo_workflow.test_cli.verify_local", side_effect=mutating_verify):
      rc = run_test(self.root, "regression", remote=False, engine_root=self.root)
    self.assertEqual(rc, 0)
    self.assertNotEqual(self.git("rev-parse", "HEAD"), candidate)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(record["testSHA"], candidate)
    self.assertTrue(record["headChangedDuringTest"])
    self.assertFalse(record["reusable"])



  def test_red_catalogue_mutation_preserves_pre_execution_fingerprint(self):
    import hashlib

    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-mutation",
    )
    source = self.root / "smoke_case.py"
    source.write_text(
      "import unittest\\n"
      "from pathlib import Path\\n"
      "class Smoke(unittest.TestCase):\\n"
      "  def test_modify_catalogue(self):\\n"
      "    path = Path('.ci/tests.json')\\n"
      "    path.write_bytes(path.read_bytes() + b' ')\\n"
      "    self.fail('RED defect observed')\\n"
    )
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-545-mutation\\n")
    self.git("add", ".ci/tests.json", "smoke_case.py", ".ci/red-green.txt")
    self.git("commit", "-m", "fixture RED catalogue mutation")
    catalogue = self.root / ".ci/tests.json"
    expected = hashlib.sha256(catalogue.read_bytes()).hexdigest()
    result = self.cli("test", "RED")
    self.assertEqual(result.returncode, 2)
    self.assertNotEqual(
      hashlib.sha256(catalogue.read_bytes()).hexdigest(), expected,
    )
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(record["catalogueSHA256"], expected)
    self.assertIn(".ci/tests.json", record["uncommittedChanges"])
    self.assertFalse(record["reusable"])


if __name__ == "__main__":
  unittest.main()
