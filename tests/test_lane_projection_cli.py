from pathlib import Path
import contextlib
import io
import unittest
from unittest import mock

from repo_workflow.command_grammar import (
  Context,
  completion_items,
  parse_tokens,
)
from repo_workflow.lane_projection import ProjectionRule
from repo_workflow.lane_selection import LaneSelection, LaneSelectionSnapshot
from repo_workflow.lane_selection_cli import (
  _selection_arguments,
  handle_lane_selection,
)
from repo_workflow.public_commands import COMMANDS
from repo_workflow.state_store import WriterIdentity


class LaneProjectionCliTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."), legal_only=False)

  def test_public_grammar_accepts_projection_modes_for_all_rule_actions(self):
    cases = (
      ["lanes", "select", "5", "--dependencies"],
      ["lanes", "select", "add", "5", "--dependents"],
      ["lanes", "select", "remove", "5", "--single"],
      ["lanes", "select", "exclude", "5"],
    )
    for words in cases:
      with self.subTest(words=words):
        self.assertEqual(
          parse_tokens(COMMANDS, self.context, words),
          tuple(words),
        )

  def test_public_completion_exposes_new_modes_not_retired_controls(self):
    items = completion_items(
      COMMANDS,
      self.context,
      ["lanes", "select", "5", ""],
    )
    tokens = {item.token for item in items}
    self.assertTrue(
      {"--dependencies", "--dependents", "--single"} <= tokens
    )
    self.assertNotIn("--follow", tokens)
    self.assertNotIn("--show-children", tokens)

  def test_parser_allows_switches_in_arbitrary_positions(self):
    self.assertEqual(
      _selection_arguments([
        "--refresh",
        "5",
        "--dependents",
        "7",
        "--json",
      ]),
      (["5", "7"], "dependents", True, False, True),
    )

  def test_parser_rejects_multiple_direction_modes(self):
    with self.assertRaisesRegex(ValueError, "mutually exclusive"):
      _selection_arguments([
        "5",
        "--dependencies",
        "--single",
      ])

  def test_select_defaults_to_both_rule(self):
    store = mock.Mock()
    store.read.return_value = LaneSelectionSnapshot(None, None)
    store.select_rules.return_value = LaneSelectionSnapshot(
      LaneSelection(
        roots=("5",),
        closure=("5",),
        graph_revision=1,
        assignment={"5": "A"},
        includes=(ProjectionRule("5", "both"),),
      ),
      1,
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
      contextlib.redirect_stdout(stdout),
    ):
      handle_lane_selection(
        Path("."),
        ["lanes", "select", "5", "--json"],
      )

    store.select_rules.assert_called_once_with(
      (ProjectionRule("5", "both"),),
      mock.ANY,
      expected_revision=None,
    )

  def test_remove_matches_seed_and_mode(self):
    current = LaneSelection(
      roots=("5",),
      closure=("5",),
      graph_revision=1,
      assignment={"5": "A"},
      includes=(
        ProjectionRule("5", "both"),
        ProjectionRule("5", "single"),
      ),
    )
    store = mock.Mock()
    store.read.return_value = LaneSelectionSnapshot(current, 9)
    store.remove_rules.return_value = LaneSelectionSnapshot(current, 10)
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
        return_value=(),
      ),
    ):
      handle_lane_selection(
        Path("."),
        ["lanes", "select", "remove", "5", "--single"],
      )

    store.remove_rules.assert_called_once_with(
      (ProjectionRule("5", "single"),),
      mock.ANY,
      expected_revision=9,
    )

  def test_exclude_adds_subtraction_rule(self):
    current = LaneSelection(
      roots=("5",),
      closure=("5",),
      graph_revision=1,
      assignment={"5": "A"},
      includes=(ProjectionRule("5", "both"),),
    )
    store = mock.Mock()
    store.read.return_value = LaneSelectionSnapshot(current, 9)
    store.exclude_rules.return_value = LaneSelectionSnapshot(current, 10)
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
        return_value=(),
      ),
    ):
      handle_lane_selection(
        Path("."),
        ["lanes", "select", "exclude", "5", "--dependents"],
      )

    store.exclude_rules.assert_called_once_with(
      (ProjectionRule("5", "dependents"),),
      mock.ANY,
      expected_revision=9,
    )


if __name__ == "__main__":
  unittest.main()
