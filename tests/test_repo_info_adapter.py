from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.repo_info_adapter import (
  RepoInfoError,
  issue_info,
  list_open_issues,
  repository_info,
)
from tests.support import RepoFixture


class RepoInfoAdapterTests(unittest.TestCase):
  def fixture(self, root: Path, body: str) -> dict:
    RepoFixture(root)
    script = root / "scripts" / "info.py"
    script.write_text(body, encoding="utf-8")
    return {"infoCommand": [sys.executable, str(script)]}

  def test_forwards_all_semantic_operations_and_normalizes_results(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args == ['repository']:\n"
        "  print(json.dumps({'schema_version': 1, 'repository': 'o/r', 'provider': 'test'}))\n"
        "elif args == ['issue', 'get', '64']:\n"
        "  print(json.dumps({'schema_version': 1, 'number': 64, 'title': 'Start', 'state': 'open'}))\n"
        "elif args == ['issue', 'list-open']:\n"
        "  print(json.dumps({'schema_version': 1, 'issues': [{'number': 2, 'title': 'B'}, {'number': 64, 'title': 'Start'}]}))\n"
        "else:\n"
        "  raise SystemExit(9)\n",
      )
      self.assertEqual(repository_info(root, config)["repository"], "o/r")
      self.assertEqual(issue_info(root, config, 64)["state"], "open")
      self.assertEqual(
        [item["number"] for item in list_open_issues(root, config)["issues"]],
        [2, 64],
      )

  def test_empty_open_list_is_success(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "print('{\"schema_version\": 1, \"issues\": []}')\n",
      )
      self.assertEqual(list_open_issues(root, config)["issues"], [])

  def test_provider_failure_is_not_empty_success(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(7)\n",
      )
      with self.assertRaisesRegex(RepoInfoError, "provider unavailable"):
        list_open_issues(root, config)

  def test_malformed_schema_fields_and_issue_identity_fail(self):
    cases = [
      ("print('not-json')\n", "malformed JSON"),
      ("print('{\"schema_version\": 2, \"number\": 64, \"title\": \"x\", \"state\": \"open\"}')\n", "unsupported"),
      ("print('{\"schema_version\": 1, \"number\": 64, \"title\": \"x\", \"state\": \"open\", \"raw\": {}}')\n", "invalid issue result"),
      ("print('{\"schema_version\": 1, \"number\": 65, \"title\": \"x\", \"state\": \"open\"}')\n", "wrong issue number"),
    ]
    for body, message in cases:
      with self.subTest(message=message), tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        config = self.fixture(root, body)
        with self.assertRaisesRegex(RepoInfoError, message):
          issue_info(root, config, 64)

  def test_open_list_requires_positive_sorted_unique_exact_entries(self):
    bad_lists = [
      [{"number": 0, "title": "zero"}],
      [{"number": 2, "title": "B"}, {"number": 1, "title": "A"}],
      [{"number": 1, "title": "A"}, {"number": 1, "title": "Again"}],
      [{"number": 1, "title": "A", "state": "open"}],
    ]
    for issues in bad_lists:
      with self.subTest(issues=issues), tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        payload = json.dumps({"schema_version": 1, "issues": issues})
        config = self.fixture(root, f"print({payload!r})\n")
        with self.assertRaises(RepoInfoError):
          list_open_issues(root, config)

  def test_read_operation_cannot_modify_repository(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "from pathlib import Path\n"
        "Path('side-effect').write_text('bad')\n"
        "print('{\"schema_version\": 1, \"repository\": \"o/r\", \"provider\": \"test\"}')\n",
      )
      with self.assertRaisesRegex(RepoInfoError, "modified repository state"):
        repository_info(root, config)

  def test_missing_adapter_configuration_fails_explicitly(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      with self.assertRaisesRegex(RepoInfoError, "not configured"):
        repository_info(root, {})


if __name__ == "__main__":
  unittest.main()
