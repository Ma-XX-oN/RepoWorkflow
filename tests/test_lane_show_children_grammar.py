from pathlib import Path
import unittest

from repo_workflow.command_grammar import CommandGrammarError, Context, parse_tokens
from repo_workflow.public_commands import COMMANDS


class LaneShowChildrenGrammarTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."), legal_only=False)

  def test_show_children_is_no_longer_public_lane_selection_grammar(self):
    with self.assertRaises(CommandGrammarError):
      parse_tokens(
        COMMANDS,
        self.context,
        ["lanes", "select", "5", "--show-children", "feature"],
      )


if __name__ == "__main__":
  unittest.main()
