from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class IssueListTests(unittest.TestCase):
  def fixture(self, root: Path, *, mode: str = "valid") -> None:
    RepoFixture(root)
    script = root / "scripts" / "info.py"
    script.write_text(
      "import json, sys\n"
      "args = sys.argv[1:]\n"
      "number = int(args[-1])\n"
      + (
        "raise SystemExit(7)\n"
        if mode == "failure"
        else "print('not-json')\n"
        if mode == "malformed"
        else
        "print(json.dumps({'schema_version': 1, 'number': number, "
        "'title': f'Issue {number}', 'state': 'open', "
        "'link': f'https://example.invalid/issues/{number}'}))\n"
      ),
      encoding="utf-8",
    )
    path = root / ".ci" / "repoworkflow.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["infoCommand"] = [sys.executable, str(script)]
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

  def run_cli(self, root: Path, *args: str):
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *args],
      capture_output=True,
      text=True,
    )

  def test_preserves_supplied_order(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root)
      result = self.run_cli(root, "issue", "list", "54", "9", "64")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(result.stdout.splitlines(), [
        "#54  Issue 54",
        "#9  Issue 9",
        "#64  Issue 64",
      ])

  def test_links_are_displayed_when_requested(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root)
      result = self.run_cli(root, "issue", "list", "54", "9", "--links")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(result.stdout.splitlines(), [
        "#54  Issue 54  https://example.invalid/issues/54",
        "#9  Issue 9  https://example.invalid/issues/9",
      ])

  def test_invalid_issue_number_and_option_position_fail(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root)
      for args in [
        ("issue", "list", "0"),
        ("issue", "list", "abc"),
        ("issue", "list", "54", "--links", "9"),
      ]:
        with self.subTest(args=args):
          result = self.run_cli(root, *args)
          self.assertEqual(result.returncode, 2)
          self.assertIn("RepoWorkflow error:", result.stderr)

  def test_malformed_provider_result_fails_explicitly(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root, mode="malformed")
      result = self.run_cli(root, "issue", "list", "54")
      self.assertNotEqual(result.returncode, 0)
      self.assertIn("malformed JSON", result.stderr)

  def test_provider_failure_fails_explicitly(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root, mode="failure")
      result = self.run_cli(root, "issue", "list", "54")
      self.assertNotEqual(result.returncode, 0)
      self.assertIn("repository information adapter failed", result.stderr)


if __name__ == "__main__":
  unittest.main()
