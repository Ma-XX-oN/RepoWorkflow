"""Independent zero/one/many/invalid RED selection acceptance via shipped rwf."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "rwf"


class SelectionLifecycleAcceptanceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not LAUNCHER.exists():
      raise unittest.SkipTest("PENDING #545: ./rwf unavailable")
    result = subprocess.run(
      [str(LAUNCHER), "test", "--help"],
      cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0 or "RED" not in result.stdout:
      raise unittest.SkipTest("PENDING #545: unified CLI not in candidate")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name) / "work"
    self.root.mkdir()
    self.git("init", "-b", "issue-629-fixture")
    self.git("config", "user.name", "Acceptance Test")
    self.git("config", "user.email", "acceptance@example.invalid")
    (self.root / "README").write_text("initial\n", encoding="utf-8")
    self.git("add", "README")
    self.git("commit", "-m", "initial source")

  def git(self, *args):
    return subprocess.run(
      ["git", "-C", str(self.root), *args],
      capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()

  def cli(self, *args):
    return subprocess.run(
      [str(LAUNCHER), "--root", str(self.root), *args],
      cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )

  def catalogue(self, names):
    path = self.root / ".ci/tests.json"
    path.parent.mkdir(exist_ok=True)
    spec = {
      "test-harnesses": {"unittest": {
        "command": "python", "layout": ["-m", "unittest", "$test"]}},
      "tests": [{"test-harness": "unittest", **{
        name: {"type": "regression", "name": "tests.test_issue629_selection_acceptance"}
        for name in names}}],
      "aliases": {},
    }
    path.write_text(json.dumps(spec), encoding="utf-8")
    self.git("add", ".ci/tests.json")
    self.git("commit", "-m", "catalogue")
    return path

  def test_zero_groups_has_no_false_red_pass(self):
    self.catalogue([])
    result = self.cli("test", "RED")
    self.assertIn("RED/GREEN", result.stdout + result.stderr)
    self.assertNotIn("RED PASS", result.stdout + result.stderr)
    selected = self.root / ".ci/red-green.txt"
    self.assertFalse(selected.exists())

  def test_one_group_is_single_persisted_selection(self):
    name = "issue-629-only"
    self.catalogue([name])
    result = self.cli("test", "RED", name)
    self.assertNotEqual(result.returncode, 0,
      "No expected-RED declaration exists; cannot pass RED")
    selection = self.root / ".ci/red-green.txt"
    self.assertEqual(selection.read_text(), name + "\n")
    self.assertEqual(self.git("show", "HEAD:.ci/red-green.txt"), name)
    self.assertEqual(self.git("show", "--format=", "--name-only", "HEAD"),
                     ".ci/red-green.txt")

  def test_many_groups_still_selects_exactly_one(self):
    first, second = "issue-629-first", "issue-629-second"
    self.catalogue([first, second])
    self.cli("test", "RED", first)
    self.assertEqual(
      (self.root / ".ci/red-green.txt").read_text(), first + "\n")
    self.cli("test", "RED", second)
    self.assertEqual(
      (self.root / ".ci/red-green.txt").read_text(), second + "\n")
    self.assertEqual(self.git("show", "HEAD:.ci/red-green.txt"), second)

  def test_invalid_foreign_or_unregistered_group_refused(self):
    name = "issue-629-valid"
    self.catalogue([name])
    baseline = self.git("rev-parse", "HEAD")
    for invalid in ("issue-628-foreign", "issue-629-unregistered"):
      with self.subTest(invalid=invalid):
        result = self.cli("test", "RED", invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), baseline)
        self.assertFalse((self.root / ".ci/red-green.txt").exists())


if __name__ == "__main__":
  unittest.main()
