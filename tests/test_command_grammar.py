from pathlib import Path
import unittest

from repo_workflow.command_grammar import (
  CommandGrammarError,
  Context,
  LAST_TERMINAL,
  completion_items,
  parse_tokens,
  validate_node,
)


class CommandGrammarTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."))

  def test_terminal_description_marks_node_executable(self):
    commands = {"run": {"": "Run it", "again": "Run again"}}
    validate_node(commands)
    self.assertEqual(parse_tokens(commands, self.context, ["run"]), ("run",))

  def test_normal_string_entry_is_terminal(self):
    commands = {"run": "Run it"}
    self.assertEqual(parse_tokens(commands, self.context, ["run"]), ("run",))

  def test_nested_node_parses_recursively(self):
    commands = {"validate": {"regression": "Run regression"}}
    self.assertEqual(
      parse_tokens(commands, self.context, ["validate", "regression"]),
      ("validate", "regression"),
    )

  def test_empty_terminal_description_is_rejected(self):
    with self.assertRaises(CommandGrammarError):
      validate_node({"run": {"": ""}})

  def test_unknown_special_key_is_rejected(self):
    with self.assertRaisesRegex(CommandGrammarError, "_for-states"):
      validate_node({"run": {"_for-states": ["ready"]}})

  def test_last_terminal_cannot_be_authored(self):
    with self.assertRaisesRegex(CommandGrammarError, LAST_TERMINAL):
      validate_node({LAST_TERMINAL: "Not a command"})

  def test_literal_bare_values_validate(self):
    validate_node({"group": {"": "Choose group", "_values": ["one", "two"]}})

  def test_literal_bare_values_reject_bad_entries(self):
    with self.assertRaises(CommandGrammarError):
      validate_node({"group": {"_values": ["one", ""]}})

  def test_callable_bare_values_parse(self):
    commands = {"group": {"_values": lambda context: ["one", "two"]}}
    self.assertEqual(
      parse_tokens(commands, self.context, ["group", "one"]),
      ("group", "one"),
    )

  def test_callable_described_fragments_parse(self):
    commands = {
      "validate": {
        "_values": lambda context: [
          {"regression": "Run regression"},
          {"integration": {"failed": "Report failure"}},
        ],
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["validate", "integration", "failed"]),
      ("validate", "integration", "failed"),
    )

  def test_callable_mixed_result_is_rejected(self):
    commands = {"x": {"_values": lambda context: ["one", {"two": "Two"}]}}
    with self.assertRaises(CommandGrammarError):
      completion_items(commands, self.context, ["x", ""])

  def test_dynamic_fragment_cannot_define_terminal_at_fragment_root(self):
    commands = {"x": {"_values": lambda context: [{"": "bad"}]}}
    with self.assertRaises(CommandGrammarError):
      completion_items(commands, self.context, ["x", ""])

  def test_dynamic_fragment_collision_is_rejected(self):
    commands = {
      "x": {
        "one": "Static",
        "_values": lambda context: [{"one": "Dynamic"}],
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "collides"):
      completion_items(commands, self.context, ["x", ""])

  def test_duplicate_dynamic_tokens_are_rejected(self):
    commands = {
      "x": {
        "_values": lambda context: [
          {"one": "First"},
          {"one": "Second"},
        ],
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "collides"):
      completion_items(commands, self.context, ["x", ""])

  def test_incomplete_prefix_is_rejected(self):
    with self.assertRaisesRegex(CommandGrammarError, "incomplete"):
      parse_tokens(
        {"validate": {"regression": "Run regression"}},
        self.context,
        ["validate"],
      )

  def test_tokens_after_terminal_are_rejected(self):
    with self.assertRaisesRegex(CommandGrammarError, "terminal command"):
      parse_tokens({"run": "Run it"}, self.context, ["run", "extra"])

  def test_bare_value_must_be_final(self):
    commands = {"group": {"_values": ["one"]}}
    with self.assertRaisesRegex(CommandGrammarError, "terminal value"):
      parse_tokens(commands, self.context, ["group", "one", "extra"])

  def test_last_terminal_is_never_parseable(self):
    commands = {"run": {"": "Run", "again": "Run again"}}
    with self.assertRaisesRegex(CommandGrammarError, "completion-only"):
      parse_tokens(commands, self.context, ["run", LAST_TERMINAL])

  def test_completion_filters_literal_prefix(self):
    commands = {"alpha": "A", "beta": "B", "alphabet": "AB"}
    self.assertEqual(
      [item.token for item in completion_items(commands, self.context, ["al"])],
      ["alpha", "alphabet"],
    )

  def test_static_completion_keeps_description(self):
    items = completion_items({"alpha": "Description"}, self.context, [""])
    self.assertEqual(items[0].description, "Description")
    self.assertFalse(items[0].bare_value)

  def test_dynamic_described_completion_keeps_description(self):
    commands = {"x": {"_values": lambda context: [{"alpha": "Dynamic"}]}}
    items = completion_items(commands, self.context, ["x", ""])
    self.assertEqual([(item.token, item.description) for item in items], [
      ("alpha", "Dynamic"),
    ])

  def test_bare_values_have_no_synthetic_description(self):
    commands = {"x": {"_values": lambda context: ["alpha"]}}
    items = completion_items(commands, self.context, ["x", ""])
    self.assertEqual(items[0].description, None)
    self.assertTrue(items[0].bare_value)

  def test_executable_node_can_present_last_terminal(self):
    commands = {"run": {"": "Run now", "again": "Run again"}}
    items = completion_items(
      commands,
      self.context,
      ["run", ""],
      include_terminal=True,
    )
    self.assertIn(LAST_TERMINAL, [item.token for item in items])


if __name__ == "__main__":
  unittest.main()
