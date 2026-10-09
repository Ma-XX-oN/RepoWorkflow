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
    for stage in ("regression", "regression"):
      previous = self.git("rev-parse", "HEAD")
      request = self.cli("test", stage, "--remote")
      self.assertEqual(request.returncode, 0, request.stderr)
      self.assertEqual(
        (self.root / ".ci/run").read_text(),
        "regression-testing " + previous + "\n",
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

  def test_failed_green_not_reusable_and_has_audit_identity(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-failing",
    )
    test_file = self.root / "smoke_case.py"
    test_file.write_text(
      test_file.read_text().replace("self.assertTrue(True)", "self.fail()")
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "failing contract test")
    (self.root / ".ci/red-green.txt").write_text("issue-545-failing\\n")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "selected failing group")
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 1, result.stderr)
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(path.read_text().splitlines()[-1])
    self.assertEqual(record["result"], "failed")
    self.assertFalse(record["reusable"])
    self.assertEqual(record["branch"], "issue-545-fixture")
    self.assertIn("timestamp", record)
    self.assertIn("architecture", record["platform"])

  def _catalogue(self, path, *, issue_group):
    (self.root / "smoke_case.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(True)\n"
    )
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
        issue_group: {"type": "regression", "name": "smoke_case"},
      }],
      "aliases": {},
    }))

  def test_selection_accepts_single_line_without_final_newline(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-selected",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-545-selected")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "select without final newline")
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(record["groups"][0]["group"], "issue-545-selected")

  def test_green_runs_only_current_issue_groups_and_records_log(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    selected = self.cli("test", "RED", "issue-545-green")
    self.assertEqual(selected.returncode, 2)
    result = self.cli("test", "GREEN")
    self.assertEqual(result.returncode, 0, result.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(record["testSHA"], self.git("rev-parse", "HEAD"))
    self.assertEqual(record["kind"], "GREEN")
    self.assertEqual(record["result"], "succeeded")
    self.assertEqual(record["groups"][0]["group"], "issue-545-green")

  def test_green_reuses_unchanged_pass_without_running_again(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 0, second.stderr)
    self.assertIn("Reusing valid PASS evidence", second.stdout)
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    self.assertEqual(len(records), 3)
    self.assertFalse(records[-2]["groups"][0]["reused"])
    self.assertTrue(records[-1]["groups"][0]["reused"])

  def test_green_does_not_reuse_pass_after_uncommitted_test_change(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    before = self.git("rev-parse", "HEAD")
    (self.root / "smoke_case.py").write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self): self.assertTrue(False)\n"
    )
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 1, second.stderr)
    self.assertNotIn("Reusing valid PASS evidence", second.stdout)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual(records[-1]["result"], "failed")
    self.assertFalse(records[-1]["groups"][0]["reused"])
    self.assertFalse(records[-1]["reusable"])
    self.assertIn("smoke_case.py", records[-1]["uncommittedChanges"])

  def test_passing_dirty_local_evidence_is_recorded_but_never_reused(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    source = self.root / "smoke_case.py"
    original = source.read_text()
    source.write_text(original + "# uncommitted local change\n")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    first_record = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(first_record["result"], "succeeded")
    self.assertFalse(first_record["reusable"])
    self.assertIn("smoke_case.py", first_record["uncommittedChanges"])
    source.write_text(original)
    second = self.cli("test", "GREEN")
    self.assertEqual(second.returncode, 0, second.stderr)
    self.assertNotIn("Reusing valid PASS evidence", second.stdout)
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    self.assertEqual(records[-1]["uncommittedChanges"], [])
    self.assertTrue(records[-1]["reusable"])
    third = self.cli("test", "GREEN")
    self.assertEqual(third.returncode, 0, third.stderr)
    self.assertIn("Reusing valid PASS evidence", third.stdout)

  def test_green_changed_catalogue_or_candidate_reexecutes(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    manifest = self.root / ".ci/tests.json"
    manifest.write_text(manifest.read_text() + " ")
    changed = self.cli("test", "GREEN")
    self.assertEqual(changed.returncode, 0, changed.stderr)
    self.assertNotIn("Reusing valid PASS evidence", changed.stdout)
    manifest.write_text(manifest.read_text().rstrip())
    (self.root / "README").write_text("changed source\n")
    self.git("add", "README")
    self.git("commit", "-m", "change candidate")
    changed_sha = self.cli("test", "GREEN")
    self.assertEqual(changed_sha.returncode, 0, changed_sha.stderr)
    self.assertNotIn("Reusing valid PASS evidence", changed_sha.stdout)

  def test_green_rejects_foreign_runner_and_platform_cache(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    baseline = json.loads(audit.read_text().splitlines()[-1])
    for field, value in (
      ("runner", "unverified-external"),
      ("platform", {"os": "wrong-os", "runtime": "0.0"}),
    ):
      with self.subTest(field=field):
        record = dict(baseline)
        record[field] = value
        audit.write_text(json.dumps(record) + "\n")
        run = self.cli("test", "GREEN")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Reusing valid PASS evidence", run.stdout)
        actual = json.loads(audit.read_text().splitlines()[-1])
        self.assertFalse(actual["groups"][0]["reused"])

  def test_green_reexecutes_after_failed_or_corrupted_cache(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    self.assertEqual(self.cli("test", "GREEN").returncode, 0)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    valid = json.loads(audit.read_text().splitlines()[-1])
    valid["result"] = "failed"
    audit.write_text(json.dumps(valid) + "\n")
    failed = self.cli("test", "GREEN")
    self.assertEqual(failed.returncode, 0, failed.stderr)
    self.assertNotIn("Reusing valid PASS evidence", failed.stdout)
    audit.write_text("{not JSON}\n")
    corrupt = self.cli("test", "GREEN")
    self.assertEqual(corrupt.returncode, 0, corrupt.stderr)
    self.assertNotIn("Reusing valid PASS evidence", corrupt.stdout)

  def test_selection_is_single_tracked_name_and_idempotent(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-selected",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    first = self.cli("test", "RED", "issue-545-selected")
    self.assertEqual(first.returncode, 2)
    selection = self.root / ".ci/red-green.txt"
    self.assertEqual(selection.read_text(), "issue-545-selected\n")
    tip = self.git("rev-parse", "HEAD")
    self.assertEqual(
      self.git("show", "--format=", "--name-only", "HEAD"),
      ".ci/red-green.txt",
    )
    repeated = self.cli("test", "RED", "issue-545-selected")
    self.assertEqual(repeated.returncode, 2)
    self.assertEqual(self.git("rev-parse", "HEAD"), tip)

  def test_actual_rwf_launcher_preserves_skip_warning_evidence(self):
    import shutil
    if shutil.which("sh") is None:
      self.skipTest("POSIX shell not installed in this environment")
    command = [
      "sh", str(ROOT / "rwf"), "--root", str(self.root), "test", "GREEN",
    ]
    result = subprocess.run(
      command, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("Warning:", result.stderr)
    output = subprocess.run(
      [
        "sh", str(ROOT / "rwf"), "--root", str(self.root),
        "test", "results",
      ],
      cwd=ROOT, capture_output=True, text=True, check=False,
    )
    self.assertEqual(output.returncode, 0, output.stderr)
    evidence = json.loads(output.stdout)
    self.assertEqual(evidence["kind"], "GREEN")
    self.assertEqual(evidence["result"], "SKIPPED")
    self.assertEqual(evidence["warning"], result.stderr.strip())
    self.assertEqual(evidence["testSHA"], self.source)

  def test_red_help_does_not_require_registered_issue_tests(self):
    result = self.cli("test", "RED", "--help")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("Run an issue-N- RED test group", result.stdout)
    self.assertIn("--remote", result.stdout)

  def test_missing_and_malformed_selection_fail_closed(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    for command in ("RED", "GREEN"):
      for remote in (False, True):
        with self.subTest(command=command, remote=remote):
          args = ("test", command, "--remote") if remote else ("test", command)
          missing = self.cli(*args)
          self.assertEqual(missing.returncode, 0, missing.stderr)
          self.assertIn("Warning:", missing.stderr)
          self.assertIn("testing skipped", missing.stdout)
          log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
          self.assertTrue(log.exists())
          records = [json.loads(line) for line in log.read_text().splitlines()]
          self.assertEqual(len(records), (
            ("RED", "GREEN").index(command) * 2 + int(remote) + 1
          ))
          record = records[-1]
          self.assertEqual(record["result"], "SKIPPED")
          self.assertEqual(record["kind"], command)
          self.assertEqual(record["testSHA"], self.source)
          self.assertEqual(record["warning"], missing.stderr.strip())
          self.assertEqual(record["reason"], "selection-file-absent")
          self.assertEqual(record["requested_remote"], remote)
          self.assertEqual(record["groups"], [])
          self.assertTrue(all(x["result"] != "succeeded" for x in records))
          self.assertFalse((self.root / ".ci/run").exists())
          self.assertEqual(self.git("rev-parse", "HEAD"), self.source)
    selection = self.root / ".ci/red-green.txt"
    for raw in ("", "issue-545-one\nissue-545-two\n",
                "issue-544-other\n", "issue-545-unlisted\n"):
      selection.write_text(raw)
      with self.subTest(raw=raw):
        result = self.cli("test", "GREEN")
        self.assertEqual(result.returncode, 2)

  def test_remote_green_uses_committed_selected_group(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-one",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.remote()
    self.assertEqual(
      self.cli("test", "RED", "issue-545-one").returncode, 2,
    )
    self.assertEqual(
      self.cli("test", "GREEN", "--remote").returncode, 0,
    )
    previous = self.git("rev-parse", "HEAD^")
    self.assertEqual(
      self.git("show", "HEAD^:.ci/red-green.txt"),
      "issue-545-one",
    )
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "GREEN-testing " + previous + "\n",
    )

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
