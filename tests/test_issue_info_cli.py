from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"


class IssueInfoCliTests(unittest.TestCase):
  def fixture(self, root: Path) -> None:
    RepoFixture(root)
    script = root / "scripts" / "info.py"
    script.write_text(
      "import json, sys\n"
      "args = sys.argv[1:]\n"
      "if args == ['issue', 'list-open']:\n"
      "  print(json.dumps({'schema_version': 1, 'issues': ["
      "{'number': 2, 'title': 'Issue 2'}, "
      "{'number': 297, 'title': 'Bootstrap help'}]}))\n"
      "elif args[:2] == ['issue', 'get']:\n"
      "  number = int(args[2])\n"
      "  print(json.dumps({'schema_version': 1, 'number': number, "
      "'title': 'Bootstrap help', 'state': 'open', "
      "'link': f'https://example.invalid/issues/{number}'}))\n"
      "else:\n"
      "  raise SystemExit(9)\n",
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

  def test_info_without_number_lists_open_issues(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root)
      completed = self.run_cli(root, "issue", "info")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(completed.stdout.splitlines(), [
        "#2  Issue 2",
        "#297  Bootstrap help",
      ])

  def test_info_with_number_renders_issue(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.fixture(root)
      completed = self.run_cli(root, "issue", "info", "297")
      self.assertEqual(completed.returncode, 0, completed.stderr)
      self.assertEqual(
        completed.stdout.strip(),
        "#297  Bootstrap help  open  https://example.invalid/issues/297",
      )


if __name__ == "__main__":
  unittest.main()
