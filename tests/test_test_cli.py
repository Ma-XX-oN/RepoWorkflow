from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class TestCliContract(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "work"
    self.root.mkdir()
    self.git("init", "-b", "issue-545-fixture")
    self.git("config", "user.name", "Test")
    self.git("config", "user.email", "test@example.invalid")
    (self.root / "README").write_text("source\n")
    self.git("add", "README")
    self.git("commit", "-m", "source")
    self.source = self.git("rev-parse", "HEAD").strip()

  def tearDown(self):
    self.temp.cleanup()

  def git(self, *args):
    completed = subprocess.run(
      ["git", "-C", str(self.root), *args],
      capture_output=True,
      text=True,
      check=True,
    )
    return completed.stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(self.root), *args],
      capture_output=True, text=True, check=False,
    )

  def remote(self):
    bare = Path(self.temp.name) / "server.git"
    subprocess.run(
      ["git", "init", "--bare", str(bare)],
      capture_output=True, check=True,
    )
    self.git("remote", "add", "origin", str(bare))
    self.git("push", "-u", "origin", "HEAD")
    return bare

  def test_help_lists_all_stages_and_remote(self):
    root = self.cli("test", "--help")
    self.assertEqual(root.returncode, 0, root.stderr)
    for name in (
      "RED", "temporary", "GREEN", "regression", "integration", "results",
    ):
      self.assertIn(name, root.stdout)
      stage = self.cli("test", name, "--help")
      if name != "RED":
        self.assertEqual(stage.returncode, 0, stage.stderr)
        self.assertIn("--remote", stage.stdout)
      else:
        self.assertIn(".ci/tests.json", stage.stderr + stage.stdout)

  def test_legacy_validate_commands_are_not_public(self):
    for stage in ("regression", "integration"):
      with self.subTest(stage=stage):
        result = self.cli("validate", stage)
        self.assertNotEqual(result.returncode, 0)

  def test_invalid_and_bare_stage_fail(self):
    for args in (("test",), ("test", "unknown"), ("test", "results", "extra")):
      with self.subTest(args=args):
        self.assertNotEqual(self.cli(*args).returncode, 0)

  def test_missing_log_fails_without_claiming_pass(self):
    result = self.cli("test", "results")
    self.assertEqual(result.returncode, 2)
    self.assertIn("testing log is unavailable", result.stderr)

  def test_local_log_returns_exact_record(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True)
    record = {
      "testSHA": self.source, "kind": "regression",
      "result": "succeeded", "runner": "local",
    }
    path.write_text(json.dumps(record) + "\n")
    result = self.cli("test", "results")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout), record)

  def test_malformed_or_incomplete_log_fails(self):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True)
    for value in ("not JSON\n", '{"testSHA":"x"}\n'):
      with self.subTest(value=value):
        path.write_text(value)
        result = self.cli("test", "results")
        self.assertEqual(result.returncode, 2)

  def test_red_completion_lists_only_current_issue_groups(self):
    path = self.root / ".ci/tests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
      "test-harnesses": {
        "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]},
      },
      "tests": [{
        "test-harness": "unittest",
        "issue-545-one": {"type": "regression", "name": "tests.test_test_cli"},
        "issue-544-other": {"type": "regression", "name": "tests.test_test_cli"},
      }],
    }
    path.write_text(json.dumps(value))
    completion = self.cli("complete", "test", "RED", "")
    self.assertEqual(completion.returncode, 0, completion.stderr)
    self.assertIn("issue-545-one", completion.stdout)
    self.assertNotIn("issue-544-other", completion.stdout)
    invalid = self.cli("test", "RED", "issue-544-other")
    self.assertNotEqual(invalid.returncode, 0)

  def test_red_completion_reports_missing_test_registration(self):
    missing = self.cli("complete", "test", "RED", "")
    self.assertNotEqual(missing.returncode, 0)
    self.assertIn("RED/GREEN tests do not exist", missing.stderr)
    self.assertIn(".ci/tests.json", missing.stderr)
    self.assertIn("issue-N-", missing.stderr)

  def test_remote_request_and_retry_use_previous_tip(self):
    bare = self.remote()
    for stage in ("RED", "RED"):
      previous = self.git("rev-parse", "HEAD")
      request = self.cli("test", stage, "--remote")
      self.assertEqual(request.returncode, 0, request.stderr)
      self.assertEqual(
        (self.root / ".ci/run").read_text(),
        "RED-testing " + previous + "\n",
      )
      head = self.git("rev-parse", "HEAD")
      self.assertNotEqual(head, previous)
      self.assertEqual(self.git("rev-parse", "HEAD^"), previous)
      self.assertEqual(
        self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
        ".ci/run",
      )
      published = subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse",
         "refs/heads/issue-545-fixture"],
        text=True, capture_output=True, check=True,
      )
      self.assertEqual(published.stdout.strip(), head)

  def test_dirty_tree_rejects_remote_without_commit(self):
    self.remote()
    (self.root / "README").write_text("edited\n")
    result = self.cli("test", "regression", "--remote")
    self.assertEqual(result.returncode, 2)
    self.assertIn("working tree must be clean", result.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), self.source)

  def test_remote_results_fetches_existing_log_only(self):
    self.remote()
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    path.parent.mkdir(parents=True)
    record = {
      "testSHA": self.source, "kind": "regression",
      "result": "succeeded", "runner": "github-actions",
    }
    path.write_text(json.dumps(record) + "\n")
    self.git("add", ".repoworkflow/validation/testResults-545.jsonl")
    self.git("commit", "-m", "external result")
    self.git("push")
    path.unlink()
    current = self.git("rev-parse", "HEAD")
    result = self.cli("test", "results", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(json.loads(result.stdout), record)
    self.assertEqual(self.git("rev-parse", "HEAD"), current)

  def test_unimplemented_integration_cannot_fake_success(self):
    result = self.cli("test", "integration")
    self.assertEqual(result.returncode, 2)
    self.assertIn("not yet implemented", result.stderr)

  def _catalogue(self, path, *, issue_group):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        issue_group: {"type": "regression", "name": "tests.test_self_ci"},
      }],
      "aliases": {},
    }))

  def test_green_runs_only_current_issue_groups_and_records_log(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().strip())
    self.assertEqual(record["testSHA"], self.source)
    self.assertEqual(record["kind"], "GREEN")
    self.assertEqual(record["result"], "succeeded")
    self.assertEqual(record["groups"][0]["group"], "issue-545-green")

  def test_temporary_catalogue_runs_identical_harness_format(self):
    self._catalogue(
      self.root / ".ci/temp-tests.json",
      issue_group="issue-545-temporary",
    )
    result = self.cli("test", "temporary")
    self.assertEqual(result.returncode, 0, result.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().strip())
    self.assertEqual(record["kind"], "temporary")
    self.assertEqual(record["result"], "succeeded")

  def test_empty_temporary_manifest_never_claims_pass(self):
    (self.root / ".ci").mkdir(exist_ok=True)
    (self.root / ".ci/temp-tests.json").write_text(json.dumps({
      "test-harnesses": {}, "tests": [], "aliases": {},
    }))
    result = self.cli("test", "temporary")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("no temporary test groups", result.stderr)


if __name__ == "__main__":
  unittest.main()
