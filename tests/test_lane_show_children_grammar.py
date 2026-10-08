from pathlib import Path
import unittest

from repo_workflow.command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  parse_tokens,
)
from repo_workflow.public_commands import COMMANDS


class LaneShowChildrenGrammarTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."), legal_only=False)

  def test_show_children_forms_parse(self):
    cases = (
      ["lanes", "select", "5", "--show-children", "group"],
      ["lanes", "select", "5", "--show-children", "feature"],
      ["lanes", "select", "5", "--show-children", "epic"],
      ["lanes", "select", "5", "--show-children", "initiative"],
      [
        "lanes", "select", "5",
        "--show-children", "feature",
        "--show-children", "epic",
      ],
      [
        "lanes", "select", "add", "7",
        "--show-children", "initiative",
      ],
      [
        "lanes", "select", "remove", "8",
        "--show-children", "group",
      ],
    )
    for words in cases:
      with self.subTest(words=words):
        self.assertEqual(
          parse_tokens(COMMANDS, self.context, words),
          tuple(words),
        )

  def test_show_children_completion_exposes_group_kinds(self):
    items = completion_items(
      COMMANDS,
      self.context,
      ["lanes", "select", "5", "--show-children", ""],
    )
    self.assertEqual(
      [item.token for item in items],
      ["epic", "feature", "group", "initiative"],
    )

  def test_show_children_requires_group_kind(self):
    with self.assertRaises(CommandGrammarError):
      parse_tokens(
        COMMANDS,
        self.context,
        ["lanes", "select", "5", "--show-children"],
      )

  def test_show_children_does_not_accept_count(self):
    with self.assertRaises(CommandGrammarError):
      parse_tokens(
        COMMANDS,
        self.context,
        ["lanes", "select", "5", "--show-children", "feature", "2"],
      )


if __name__ == "__main__":
  unittest.main()
