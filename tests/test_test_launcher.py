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

  def test_all_six_stage_help_commands_are_reachable(self):
    for name in (
      "RED", "temporary", "GREEN", "regression", "integration", "results",
    ):
      with self.subTest(stage=name):
        out = self.launcher("test", name, "--help")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--remote", out.stdout + out.stderr)

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
    current = self.git("rev-parse", "HEAD")
    self.assertNotEqual(current, previous)
    self.assertEqual(self.git("rev-parse", "HEAD^"), previous)
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "regression-testing " + previous + "\n",
    )
    remote_tip = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_tip, current)

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
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "register RED test")
    bare = self.remote()
    out = self.launcher("test", "RED", "issue-545-remote-red", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    head = self.git("rev-parse", "HEAD")
    selected_commit = self.git("rev-parse", "HEAD^")
    self.assertEqual(
      self.git("show", "HEAD^:.ci/red-green.txt"),
      "issue-545-remote-red",
    )
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "RED-testing " + selected_commit + "\n",
    )
    remote_head = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_head, head)

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
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "temp-testing " + before + "\n",
    )
    head = self.git("rev-parse", "HEAD")
    remote_head = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      text=True, capture_output=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_head, head)


  def test_integration_remote_request_is_a_dedicated_commit(self):
    bare = self.remote()
    before = self.git("rev-parse", "HEAD")
    out = self.launcher("test", "integration", "--remote")
    self.assertEqual(out.returncode, 0, out.stderr)
    head = self.git("rev-parse", "HEAD")
    self.assertNotEqual(head, before)
    self.assertEqual(self.git("rev-parse", "HEAD^"), before)
    self.assertEqual(
      (self.root / ".ci/run").read_text(),
      "integration-testing " + before + "\n",
    )
    remote_head = subprocess.run(
      ["git", "--git-dir", str(bare), "rev-parse",
       "refs/heads/issue-545-fixture"],
      capture_output=True, text=True, check=True,
    ).stdout.strip()
    self.assertEqual(remote_head, head)


  def test_remote_red_and_green_without_selection_are_skipped(self):
    self.remote()
    before = self.git("rev-parse", "HEAD")
    for stage in ("RED", "GREEN"):
      with self.subTest(stage=stage):
        out = self.launcher("test", stage, "--remote")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertFalse((self.root / ".ci/run").exists())

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
