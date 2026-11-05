"""Black-box acceptance tests through the actual shipped ./rwf launcher."""
from pathlib import Path
import json
import shutil
import subprocess
import unittest

from tests import test_test_cli as fixture


LAUNCHER = Path(__file__).resolve().parents[1] / "rwf"


class ShippedTestLauncher(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  remote = fixture.TestCliContract.remote
  _catalogue = fixture.TestCliContract._catalogue

  def launcher(self, *args):
    if not shutil.which("sh"):
      self.skipTest("no POSIX shell is installed for shipped rwf")
    return subprocess.run(
      ["sh", str(LAUNCHER), "--root", str(self.root), *args],
      capture_output=True, text=True, check=False,
    )

  def assert_cmd_transport(self, bare, number, source, stage):
    """Verify one CMD publication without rewriting the source branch."""
    self.assertEqual(self.git("rev-parse", "HEAD"), source)
    self.assertFalse((self.root / ".ci/run").exists())
    branch = f"CMD-{number}-issue-545-fixture"
    cmd = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse", f"refs/heads/{branch}"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(self.git("rev-parse", cmd + "^"), source)
    self.assertEqual(self.git("show", cmd + ":.ci/rwf"),
                     f"test {stage} --remote 0")
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", cmd),
      ".ci/rwf",
    )
    remote_source = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_source, source)

  def test_static_stage_help_commands_are_reachable(self):
    for name in (
      "temporary", "GREEN", "regression", "integration", "results",
    ):
      with self.subTest(stage=name):
        out = self.launcher("test", name, "--help")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--remote", out.stdout + out.stderr)

  def test_shipped_red_help_is_current_issue_aware(self):
    missing = self.launcher("test", "RED", "--help")
    tab = self.launcher("complete", "test", "RED", "")
    double = self.launcher("complete", "--describe", "test", "RED", "")
    for response in (missing, tab, double):
      self.assertEqual(response.returncode, 2, response)
      self.assertEqual(response.stdout, "")
      self.assertIn("RED/GREEN tests do not exist", response.stderr)
    self.assertEqual({x.stderr for x in (missing, tab, double)},
                     {missing.stderr})

    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-red-help",
    )
    described = self.launcher("test", "RED", "--help")
    double = self.launcher(
      "complete", "--describe", "test", "RED", "",
    )
    single = self.launcher("complete", "test", "RED", "")
    for result in (described, double, single):
      self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(described.stdout, double.stdout)
    self.assertIn("issue-545-red-help", single.stdout)
    self.assertIn("issue-545-red-help", described.stdout)

  def test_shipped_completion_lists_six_current_testing_stages(self):
    output = self.launcher("complete", "test", "")
    self.assertEqual(output.returncode, 0, output.stderr)
    for stage in (
      "RED", "temporary", "GREEN", "regression", "integration", "results",
    ):
      with self.subTest(stage=stage):
        self.assertIn(stage, output.stdout)
    self.assertNotIn("validate regression", output.stdout)


  def test_remote_switch_cannot_precede_stage_for_any_command(self):
    before = self.git("rev-parse", "HEAD")
    for name in (
      "RED", "temporary", "GREEN", "regression", "integration", "results",
    ):
      with self.subTest(stage=name):
        out = self.launcher("test", "--remote", name)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertFalse((self.root / ".ci/run").exists())

  def test_real_bare_remote_marker_uses_immediate_parent(self):
    bare = self.remote()
    previous = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "regression", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assert_cmd_transport(bare, 1, previous, "regression")

  def test_absent_red_selection_records_skipped_and_not_pass(self):
    out = self.launcher("test", "RED")
    self.assertEqual(out.returncode, 0, out.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(record["result"], "SKIPPED")
    self.assertEqual(record["kind"], "RED")
    self.assertEqual(record["testSHA"], self.source)
    self.assertFalse(record.get("reusable", False))

  def test_selected_red_remote_request_uses_committed_selection(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-remote-red",
    )
    catalogue = self.root / ".ci/tests.json"
    data = json.loads(catalogue.read_text())
    data["tests"][0]["issue-545-remote-red"]["expected-red"] = {
      "exit-code": 1, "output-contains": "specific hosted invariant",
    }
    catalogue.write_text(json.dumps(data))
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "register declared RED test")
    bare = self.remote()
    original_source = self.git("rev-parse", "HEAD")
    result = self.launcher("test", "RED", "issue-545-remote-red", "--remote")
    self.assertEqual(result.returncode, 0, result.stderr)
    selected_source = self.git("rev-parse", "HEAD")
    self.assertEqual(selected_source, original_source)
    self.assertFalse((self.root / ".ci/red-green.txt").exists())
    self.assertFalse((self.root / ".ci/run").exists())
    branch = "CMD-1-issue-545-fixture"
    self.assertIn(branch, result.stdout)
    tip = subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse",
         f"refs/heads/{branch}"],
        text=True, capture_output=True, check=True,
      ).stdout.strip()
    self.assertEqual(self.git("rev-parse", f"{tip}^"), selected_source)
    self.assertEqual(
      self.git("diff-tree", "--no-commit-id", "--name-only", "-r", tip),
      ".ci/rwf",
    )
    self.assertEqual(
      self.git("show", f"{tip}:.ci/rwf"),
      "test RED issue-545-remote-red --remote 0",
    )
    published_source = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(published_source, original_source)

  def test_missing_red_declaration_prevents_remote_publication(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-missing-remote",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "undeclared RED test")
    self.remote()
    initial = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "RED", "issue-545-missing-remote", "--remote")
    self.assertEqual(out.returncode, 2, out.stderr)
    selected = self.git("rev-parse", "HEAD")
    self.assertEqual(selected, initial)
    self.assertFalse((self.root / ".ci/red-green.txt").exists())
    self.assertIn("expected-failure-declaration-missing", out.stderr)
    self.assertFalse((self.root / ".ci/run").exists())
    after = self.git("ls-remote", "origin", "refs/heads/issue-545-fixture")
    self.assertEqual(after.split()[0], initial)


  def test_missing_remote_red_declaration_preserves_prior_selection(self):
    catalogue = self.root / ".ci/tests.json"
    self._catalogue(catalogue, issue_group="issue-545-prior-selection")
    data = json.loads(catalogue.read_text(encoding="utf-8"))
    data["tests"].append({
      "test-harness": "unittest",
      "issue-545-missing-remote": {
        "type": "regression", "name": "smoke_case",
      },
    })
    catalogue.write_text(json.dumps(data), encoding="utf-8")
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "register both issue RED groups")
    selection = self.root / ".ci/red-green.txt"
    selection.write_text("issue-545-prior-selection\n", encoding="utf-8")
    self.git("add", ".ci/red-green.txt")
    self.git("commit", "-m", "explicitly select original RED group")
    self.remote()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "RED", "issue-545-missing-remote", "--remote")
    self.assertEqual(out.returncode, 2, out.stderr)
    self.assertIn("expected-failure-declaration-missing", out.stderr)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    self.assertEqual(selection.read_text(encoding="utf-8"),
                     "issue-545-prior-selection\n")
    self.assertEqual(self.git("status", "--porcelain"), "")
    self.assertEqual(self.git("ls-remote", "origin", "refs/heads/CMD-*"), "")

  def test_temporary_remote_request_with_valid_manifest(self):
    self._catalogue(
      self.root / ".ci/temp-tests.json",
      issue_group="issue-545-remote-temp",
    )
    self.git("add", ".ci/temp-tests.json", "smoke_case.py")
    self.git("commit", "-m", "register temporary")
    bare = self.remote()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "temporary", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assert_cmd_transport(bare, 1, before, "temporary")

  def test_shipped_red_uses_predeclared_behavioural_failure(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-expected",
    )
    source = self.root / "smoke_case.py"
    source.write_text(
      "import unittest\n"
      "class Smoke(unittest.TestCase):\n"
      "  def test_pass(self):\n"
      "    self.fail('domain invariant ABC-545 violated')\n"
    )
    catalogue = self.root / ".ci/tests.json"
    value = json.loads(catalogue.read_text())
    value["tests"][0]["issue-545-expected"]["expected-red"] = {
      "exit-code": 1,
      "output-contains": "domain invariant ABC-545 violated",
    }
    catalogue.write_text(json.dumps(value))
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "explicit behavioural expectation")
    for attempt in range(2):
      with self.subTest(attempt=attempt):
        words = (
          ("test", "RED", "issue-545-expected") if attempt == 0
          else ("test", "RED")
        )
        out = self.launcher(*words)
        self.assertEqual(out.returncode, 0, out.stderr)
        log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
        record = json.loads(log.read_text().splitlines()[-1])
        self.assertEqual(record["redStatus"], "RED")
        self.assertEqual(record["result"], "succeeded")
        self.assertFalse(record["reusable"])


  def test_integration_remote_request_is_a_dedicated_commit(self):
    bare = self.remote()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "integration", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assert_cmd_transport(bare, 1, before, "integration")

  def test_remote_red_and_green_without_selection_submit_cmd(self):
    bare = self.remote()
    before = self.git("rev-parse", "HEAD")
    for number, stage in enumerate(("RED", "GREEN"), start=1):
      with self.subTest(stage=stage):
        out = self.launcher("test", stage, "--remote")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assert_cmd_transport(bare, number, before, stage)

  def test_missing_temporary_manifest_rejects_valid_remote_placement(self):
    self.remote()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "temporary", "--remote")
    self.assertEqual(out.returncode, 2, out.stderr)
    self.assertNotIn("invalid command", out.stderr.lower())
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    self.assertFalse((self.root / ".ci/run").exists())

  def test_shipped_remote_results_fetches_without_new_request(self):
    bare = self.remote()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    log.parent.mkdir(parents=True)
    expected = {
      "testSHA": self.source, "kind": "regression",
      "result": "succeeded", "runner": "github-actions",
    }
    log.write_text(json.dumps(expected) + "\n")
    self.git("add", ".repoworkflow/validation/testResults-545.jsonl")
    self.git("commit", "-m", "published provider observation")
    self.git("push")
    log.unlink()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "results", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assertEqual(json.loads(out.stdout), expected)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    self.assertFalse((self.root / ".ci/run").exists())
    remote_head = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_head, before)


  def test_results_are_read_only_through_shipped_launcher(self):
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    log.parent.mkdir(parents=True)
    expected = {
      "testSHA": self.source, "kind": "regression",
      "result": "succeeded", "runner": "local",
    }
    log.write_text(json.dumps(expected) + "\n")
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "results")
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assertEqual(json.loads(out.stdout), expected)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)


if __name__ == "__main__":
  unittest.main()
