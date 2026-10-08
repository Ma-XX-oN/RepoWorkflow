from __future__ import annotations

import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from repo_workflow.command_grammar import Context, parse_tokens
from repo_workflow.lane_selection import (
  LaneSelection,
  LaneSelectionSnapshot,
  LaneSelectionStore,
)
from repo_workflow.lane_selection_cli import handle_lane_selection
from repo_workflow.public_commands import COMMANDS
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"
CANONICAL_TICKETS = ROOT / ".repoworkflow" / "tickets.csv"


def relation(title: str, *dependencies: int) -> IssueRelationships:
  return IssueRelationships(title, tuple(str(value) for value in dependencies))


def canonical_rows() -> dict[str, dict[str, str]]:
  with CANONICAL_TICKETS.open(
    newline="",
    encoding="utf-8",
  ) as handle:
    return {
      row["issue"]: row
      for row in csv.DictReader(handle)
    }


def expected_default_closure(
  rows: dict[str, dict[str, str]],
  seed: str,
) -> tuple[str, ...]:
  dependencies = {
    issue: tuple(
      value
      for value in row["dependencies"].split(";")
      if value
    )
    for issue, row in rows.items()
  }
  dependants = {issue: set() for issue in rows}
  for issue, values in dependencies.items():
    for dependency in values:
      if dependency in dependants:
        dependants[dependency].add(issue)

  def closure(adjacency):
    seen = set()
    pending = [seed]
    while pending:
      issue = pending.pop()
      if issue in seen:
        continue
      seen.add(issue)
      pending.extend(
        value
        for value in adjacency[issue]
        if value not in seen
      )
    return seen

  return tuple(sorted(
    closure(dependencies) | closure(dependants),
    key=int,
  ))


class LaneCountTests(unittest.TestCase):
  def test_count_switch_is_unordered_in_public_grammar(self):
    context = Context(Path("."), legal_only=False)
    cases = (
      ["lanes", "select", "5", "--count", "--dependencies"],
      ["lanes", "select", "--count", "5", "--dependents"],
      ["lanes", "select", "--single", "5", "--count"],
    )
    for words in cases:
      with self.subTest(words=words):
        parse_tokens(COMMANDS, context, words)

  def test_projection_is_read_only_and_matches_normal_select(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      writer = WriterIdentity("agent", "session")
      relationships = RelationshipStore(root)
      relationships.create(
        RelationshipGraph(issues={
          "1": relation("Issue 1"),
          "2": relation("Issue 2", 1),
          "3": relation("Feature: Boundary", 2),
          "4": relation("Issue 4", 3),
        }),
        writer,
      )
      store = LaneSelectionStore(root)

      before = store.read()
      projected = store.project((2,))
      after = store.read()

      self.assertEqual(before, after)
      self.assertEqual(projected.roots, ("2",))
      self.assertEqual(projected.closure, ("1", "2", "3", "4"))

      selected = store.select((2,), writer)
      self.assertEqual(projected.closure, selected.value.closure)
      self.assertEqual(projected.assignment, selected.value.assignment)

  def test_count_prints_bare_integer_and_never_renders_or_persists(self):
    store = mock.Mock()
    store.read.return_value = LaneSelectionSnapshot(None, None)
    store.project_rules.return_value = LaneSelection(
      roots=("2",),
      closure=("1", "2", "3"),
      graph_revision=7,
      assignment={"1": "A", "2": "A", "3": "A"},
    )
    stdout = io.StringIO()
    with (
      mock.patch(
        "repo_workflow.lane_selection_cli.LaneSelectionStore",
        return_value=store,
      ),
      mock.patch(
        "repo_workflow.lane_selection_cli.runtime_writer_identity",
        return_value=WriterIdentity("agent", "session"),
      ),
      mock.patch("repo_workflow.lane_selection_cli._prepare"),
      mock.patch(
        "repo_workflow.lane_selection_cli.render_lanes",
        side_effect=AssertionError("renderer must not run"),
      ),
      contextlib.redirect_stdout(stdout),
    ):
      result = handle_lane_selection(
        Path("."),
        ["lanes", "select", "2", "--count"],
      )

    self.assertEqual(result, 0)
    self.assertEqual(stdout.getvalue(), "3\n")
    store.project_rules.assert_called_once()
    store.select_rules.assert_not_called()
    store.add_rules.assert_not_called()
    store.remove_rules.assert_not_called()
    store.exclude_rules.assert_not_called()

  def test_canonical_413_count_matches_independent_projection_without_rendering(self):
    rows = canonical_rows()
    expected = expected_default_closure(rows, "413")
    self.assertEqual(expected, ("409", "410", "411", "412", "413", "456"))

    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      RepoFixture(root)
      target = root / ".repoworkflow" / "tickets.csv"
      target.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(CANONICAL_TICKETS, target)

      issues = {}
      dependencies = {}
      for issue, row in rows.items():
        issues[issue] = row["title"]
        dependencies[issue] = [
          int(value)
          for value in row["dependencies"].split(";")
          if value
        ]
      dependants = {issue: [] for issue in issues}
      for issue, values in dependencies.items():
        for dependency in values:
          dependants[str(dependency)].append(int(issue))

      data = root / "issues.json"
      data.write_text(
        json.dumps({
          "issues": issues,
          "dependencies": dependencies,
          "dependants": {
            issue: sorted(values)
            for issue, values in dependants.items()
          },
        }, sort_keys=True) + "\n",
        encoding="utf-8",
      )
      script = root / "scripts" / "canonical_count_info.py"
      script.write_text(
        "import json, pathlib, sys\n"
        "data = json.loads((pathlib.Path(__file__).parents[1] / "
        "'issues.json').read_text(encoding='utf-8'))\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['dependency', 'related']:\n"
        "  number = str(int(args[2]))\n"
        "  print(json.dumps({\n"
        "    'schema_version': 1,\n"
        "    'issue': int(number),\n"
        "    'dependencies': data['dependencies'][number],\n"
        "    'dependants': data['dependants'][number],\n"
        "  }))\n"
        "else:\n"
        "  number = str(int(args[-1]))\n"
        "  print(json.dumps({\n"
        "    'schema_version': 1,\n"
        "    'number': int(number),\n"
        "    'title': data['issues'][number],\n"
        "    'state': 'open',\n"
        "    'link': f'https://example.invalid/issues/{number}',\n"
        "  }))\n",
        encoding="utf-8",
      )
      config_path = root / ".ci" / "repoworkflow.json"
      config = json.loads(config_path.read_text(encoding="utf-8"))
      config["infoCommand"] = [sys.executable, str(script)]
      config["dependencyCommand"] = [sys.executable, str(script)]
      config_path.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
      )

      before_selection = root / ".git" / "repoworkflow" / "lane-selection"
      before = (
        tuple(sorted(
          (path.relative_to(before_selection), path.read_bytes())
          for path in before_selection.rglob("*")
          if path.is_file()
        ))
        if before_selection.exists()
        else ()
      )

      result = subprocess.run(
        [
          str(RWF),
          "--root",
          str(root),
          "lanes",
          "select",
          "413",
          "--count",
        ],
        cwd=root,
        capture_output=True,
        text=True,
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(result.stdout, f"{len(expected)}\n")

      after = (
        tuple(sorted(
          (path.relative_to(before_selection), path.read_bytes())
          for path in before_selection.rglob("*")
          if path.is_file()
        ))
        if before_selection.exists()
        else ()
      )
      self.assertEqual(after, before)


if __name__ == "__main__":
  unittest.main()
