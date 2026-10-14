from pathlib import Path
import unittest

from repo_workflow.command_grammar import Context, completion_items, parse_tokens
from repo_workflow.public_commands import COMMANDS


class LaneFollowGrammarTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."), legal_only=False)

  def test_follow_forms_parse_through_public_grammar(self):
    cases = (
      ["lanes", "select", "5", "--follow", "initiative"],
      ["lanes", "select", "5", "--follow", "feature", "2"],
      [
        "lanes", "select", "5",
        "--follow", "feature", "2",
        "--follow", "epic",
      ],
      ["lanes", "select", "add", "7", "--follow", "feature"],
      ["lanes", "select", "remove", "8", "--follow", "epic", "2"],
    )
    for words in cases:
      with self.subTest(words=words):
        self.assertEqual(
          parse_tokens(COMMANDS, self.context, words),
          tuple(words),
        )

  def test_follow_completion_exposes_group_kinds(self):
    items = completion_items(
      COMMANDS,
      self.context,
      ["lanes", "select", "5", "--follow", ""],
    )
    self.assertEqual(
      [item.token for item in items],
      ["epic", "feature", "group", "initiative"],
    )

  def test_follow_help_exposes_optional_count_position(self):
    items = completion_items(
      COMMANDS,
      self.context,
      ["lanes", "select", "5", "--follow", "feature", ""],
      include_terminal=True,
      describe=True,
    )
    self.assertIn("<N>", [item.token for item in items])

  def test_follow_switch_may_repeat_for_distinct_types(self):
    words = [
      "lanes", "select", "5",
      "--follow", "feature",
      "--follow", "epic", "2",
      "--follow", "initiative",
    ]
    self.assertEqual(
      parse_tokens(COMMANDS, self.context, words),
      tuple(words),
    )


if __name__ == "__main__":
  unittest.main()
