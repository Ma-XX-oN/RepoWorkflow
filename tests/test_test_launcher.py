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
