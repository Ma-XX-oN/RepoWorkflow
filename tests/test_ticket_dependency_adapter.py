from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.ticket_dependency_adapter import (
  TicketDependencyError,
  read_ticket_dependencies,
  read_ticket_relationships,
  replace_ticket_dependencies,
)
from tests.support import RepoFixture


class TicketDependencyAdapterTests(unittest.TestCase):
  def fixture(self, root: Path, body: str) -> dict:
    RepoFixture(root)
    script = root / "scripts" / "dependencies.py"
    script.write_text(body, encoding="utf-8")
    return {"dependencyCommand": [sys.executable, str(script)]}

  def test_read_and_replace_forward_provider_neutral_operations(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "issue = int(args[2])\n"
        "deps = [2, 9] if args[1] == 'get' else sorted(map(int, args[3:]))\n"
        "print(json.dumps({'schema_version': 1, 'issue': issue, 'dependencies': deps}))\n",
      )
      self.assertEqual(read_ticket_dependencies(root, config, 64), (2, 9))
      self.assertEqual(
        replace_ticket_dependencies(root, config, 64, [9, 2, 9]),
        (2, 9),
      )
      self.assertEqual(replace_ticket_dependencies(root, config, 64, []), ())

  def test_related_read_returns_both_direct_relationship_directions(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "import json, sys\n"
        "issue = int(sys.argv[3])\n"
        "print(json.dumps({\n"
        "  'schema_version': 1, 'issue': issue,\n"
        "  'dependencies': [2, 9], 'dependants': [70, 81],\n"
        "}))\n",
      )
      value = read_ticket_relationships(root, config, 64)
      self.assertEqual(value.dependencies, (2, 9))
      self.assertEqual(value.dependants, (70, 81))

  def test_related_read_validates_dependants_strictly(self):
    payloads = [
      json.dumps({
        "schema_version": 1,
        "issue": 64,
        "dependencies": [],
        "dependants": [81, 70],
      }),
      json.dumps({
        "schema_version": 1,
        "issue": 64,
        "dependencies": [],
        "dependants": [70, 70],
      }),
      json.dumps({
        "schema_version": 1,
        "issue": 64,
        "dependencies": [],
        "dependants": [64],
      }),
    ]
    for payload in payloads:
      with self.subTest(payload=payload), tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        config = self.fixture(root, f"print({payload!r})\n")
        with self.assertRaises(TicketDependencyError):
          read_ticket_relationships(root, config, 64)

  def test_empty_read_is_success_but_provider_failure_is_not(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "print('{\"schema_version\":1,\"issue\":64,\"dependencies\":[]}')\n",
      )
      self.assertEqual(read_ticket_dependencies(root, config, 64), ())

    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "import sys\nprint('unsupported', file=sys.stderr)\nraise SystemExit(7)\n",
      )
      with self.assertRaisesRegex(TicketDependencyError, "unsupported"):
        read_ticket_dependencies(root, config, 64)

  def test_strict_result_validation(self):
    payloads = [
      "not-json",
      json.dumps({"schema_version": 2, "issue": 64, "dependencies": []}),
      json.dumps({"schema_version": 1, "issue": 65, "dependencies": []}),
      json.dumps({"schema_version": 1, "issue": 64, "dependencies": [9, 2]}),
      json.dumps({"schema_version": 1, "issue": 64, "dependencies": [2, 2]}),
      json.dumps({"schema_version": 1, "issue": 64, "dependencies": [64]}),
      json.dumps({
        "schema_version": 1, "issue": 64, "dependencies": [], "raw": {}
      }),
    ]
    for payload in payloads:
      with self.subTest(payload=payload), tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        config = self.fixture(root, f"print({payload!r})\n")
        with self.assertRaises(TicketDependencyError):
          read_ticket_dependencies(root, config, 64)

  def test_replace_requires_exact_confirmation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "print('{\"schema_version\":1,\"issue\":64,\"dependencies\":[2]}')\n",
      )
      with self.assertRaisesRegex(TicketDependencyError, "did not confirm"):
        replace_ticket_dependencies(root, config, 64, [2, 9])

  def test_adapter_cannot_modify_local_repository(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      config = self.fixture(
        root,
        "from pathlib import Path\n"
        "Path('side-effect').write_text('bad')\n"
        "print('{\"schema_version\":1,\"issue\":64,\"dependencies\":[]}')\n",
      )
      with self.assertRaisesRegex(TicketDependencyError, "modified repository"):
        read_ticket_dependencies(root, config, 64)

  def test_missing_configuration_and_self_dependency_fail(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      with self.assertRaisesRegex(TicketDependencyError, "not configured"):
        read_ticket_dependencies(root, {}, 64)
      with self.assertRaisesRegex(TicketDependencyError, "self dependency"):
        replace_ticket_dependencies(root, {}, 64, [64])


if __name__ == "__main__":
  unittest.main()
