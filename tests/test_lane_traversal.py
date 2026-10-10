import unittest

from repo_workflow.lane_selection_cli import _selection_arguments
from repo_workflow.lane_traversal import (
  FollowPolicy,
  LaneTraversalError,
  group_kind,
  parse_follow_arguments,
)


class LaneTraversalTests(unittest.TestCase):
  def test_group_kind_uses_synchronized_title_prefixes(self):
    self.assertEqual(group_kind("Feature: One"), "feature")
    self.assertEqual(group_kind("Epic: Two"), "epic")
    self.assertEqual(group_kind("Initiative: Three"), "initiative")
    self.assertIsNone(group_kind("Issue 4"))
    self.assertIsNone(group_kind("feature: lower-case is ordinary"))

  def test_legacy_follow_policy_parser_remains_deterministic(self):
    self.assertEqual(
      parse_follow_arguments([("feature", None)]),
      FollowPolicy(feature=1),
    )
    for value in ("0", "-1", "x", ""):
      with self.subTest(value=value):
        with self.assertRaises(LaneTraversalError):
          parse_follow_arguments([("epic", value)])

  def test_selection_parser_extracts_dependencies_mode(self):
    positional, mode, as_json, count_only, refresh = _selection_arguments([
      "5",
      "--dependencies",
      "6",
      "--refresh",
      "--json",
    ])
    self.assertEqual(positional, ["5", "6"])
    self.assertEqual(mode, "dependencies")
    self.assertTrue(as_json)
    self.assertFalse(count_only)
    self.assertTrue(refresh)

  def test_selection_parser_defaults_to_both(self):
    positional, mode, as_json, count_only, refresh = _selection_arguments(["5"])
    self.assertEqual(positional, ["5"])
    self.assertEqual(mode, "both")
    self.assertFalse(as_json)
    self.assertFalse(count_only)
    self.assertFalse(refresh)

  def test_direction_switches_are_mutually_exclusive(self):
    with self.assertRaisesRegex(ValueError, "mutually exclusive"):
      _selection_arguments([
        "5",
        "--dependencies",
        "--dependents",
      ])

  def test_obsolete_follow_switch_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "unsupported"):
      _selection_arguments(["5", "--follow", "epic"])


if __name__ == "__main__":
  unittest.main()
