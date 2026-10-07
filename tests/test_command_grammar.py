from pathlib import Path
import unittest

from repo_workflow.public_commands import COMMANDS
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

  def test_literal_values_are_rejected(self):
    with self.assertRaises(CommandGrammarError):
      validate_node({"group": {"": "Choose group", "_values": ["one", "two"]}})

  def test_provider_rejects_bad_bare_completion_entries(self):
    commands = {
      "group": {
        "_values": lambda context: {"completions": ["one", ""]},
      },
    }
    with self.assertRaises(CommandGrammarError):
      completion_items(commands, self.context, ["group", ""])

  def test_callable_bare_values_parse(self):
    commands = {
      "group": {
        "_values": lambda context: {"completions": ["one", "two"]},
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["group", "one"]),
      ("group", "one"),
    )

  def test_callable_described_fragments_parse(self):
    commands = {
      "validate": {
        "_values": lambda context: {
          "completions": [
            {"regression": "Run regression"},
            {"integration": {"failed": "Report failure"}},
          ],
        },
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["validate", "integration", "failed"]),
      ("validate", "integration", "failed"),
    )

  def test_completion_spec_can_mix_bare_and_described_entries(self):
    commands = {
      "x": {
        "_values": lambda context: {
          "completions": ["one", {"two": "Two"}],
        },
      },
    }
    items = completion_items(commands, self.context, ["x", ""])
    self.assertEqual(
      [(item.token, item.description) for item in items],
      [("one", None), ("two", "Two")],
    )

  def test_dynamic_fragment_cannot_define_terminal_at_fragment_root(self):
    commands = {"x": {"_values": lambda context: {"completions": [{"": "bad"}]}}}
    with self.assertRaises(CommandGrammarError):
      completion_items(commands, self.context, ["x", ""])

  def test_dynamic_fragment_collision_is_rejected(self):
    commands = {
      "x": {
        "one": "Static",
        "_values": lambda context: {"completions": [{"one": "Dynamic"}]},
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "collides"):
      completion_items(commands, self.context, ["x", ""])

  def test_duplicate_dynamic_tokens_are_rejected(self):
    commands = {
      "x": {
        "_values": lambda context: {
          "completions": [
            {"one": "First"},
            {"one": "Second"},
          ],
        },
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
    commands = {"group": {"_values": lambda context: {"completions": ["one"]}}}
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
    commands = {
      "x": {
        "_values": lambda context: {
          "completions": [{"alpha": "Dynamic"}],
        },
      },
    }
    items = completion_items(commands, self.context, ["x", ""])
    self.assertEqual([(item.token, item.description) for item in items], [
      ("alpha", "Dynamic"),
    ])

  def test_bare_values_have_no_synthetic_description(self):
    commands = {
      "x": {
        "_values": lambda context: {"completions": ["alpha"]},
      },
    }
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


  def test_help_projects_placeholder_for_dynamic_value_prefix(self):
    commands = {
      "issue": {
        "_values": lambda context: {"completions": []},
        "_value_description": "Issue number",
      },
    }
    items = completion_items(
      commands,
      self.context,
      ["issue", ""],
      include_terminal=True,
      describe=True,
    )
    self.assertEqual(
      [(item.token, item.description) for item in items],
      [("<value>", "Issue number")],
    )

  def test_normal_completion_does_not_invent_dynamic_value_placeholder(self):
    commands = {
      "issue": {
        "_values": lambda context: {"completions": []},
        "_value_description": "Issue number",
      },
    }
    self.assertEqual(
      completion_items(commands, self.context, ["issue", ""]),
      [],
    )

  def test_executable_dynamic_value_help_has_terminal_and_placeholder(self):
    commands = {
      "issue": {
        "": "List issues",
        "_values": lambda context: {"completions": []},
        "_value_description": "Issue number",
      },
    }
    items = completion_items(
      commands,
      self.context,
      ["issue", ""],
      include_terminal=True,
      describe=True,
    )
    self.assertEqual(
      [(item.token, item.description) for item in items],
      [
        ("<last-terminal>", "List issues"),
        ("<value>", "Issue number"),
      ],
    )

  def test_default_quantifier_accepts_exactly_one_value(self):
    commands = {
      "x": {
        "": "Run",
        "_values": lambda context: [context.current_token]
        if context.current_token else [],
      },
    }
    self.assertEqual(parse_tokens(commands, self.context, ["x", "a"]), ("x", "a"))
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x"])
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x", "a", "b"])

  def test_regex_quantifiers_cover_cardinality_boundaries(self):
    cases = {
      "?": (0, 1),
      "*": (0, 3),
      "+": (1, 3),
      "{2}": (2, 2),
      "{2,}": (2, 4),
      "{2,3}": (2, 3),
    }
    for quantifier, (minimum, maximum) in cases.items():
      with self.subTest(quantifier=quantifier):
        commands = {
          "x": {
            "": "Run",
            "_values": lambda context: [context.current_token]
            if context.current_token else [],
            "_quantifier": quantifier,
          },
        }
        accepted = tuple(["x", *(str(i) for i in range(maximum))])
        self.assertEqual(parse_tokens(commands, self.context, accepted), accepted)
        if minimum:
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", *(str(i) for i in range(minimum - 1))],
            )
        bounded = quantifier in {"?", "{2}", "{2,3}"}
        if bounded:
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", *(str(i) for i in range(maximum + 1))],
            )

  def test_switches_parse_in_arbitrary_order_with_values(self):
    commands = {
      "x": {
        "": "Run",
        "_values": lambda context: [context.current_token]
        if context.current_token and not context.current_token.startswith("--")
        else [],
        "_quantifier": "+",
        "_switches": {
          "--alpha": "Alpha",
          "--beta": "Beta",
        },
      },
    }
    for words in (
      ["x", "--alpha", "one", "--beta", "two"],
      ["x", "one", "--beta", "two", "--alpha"],
    ):
      self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))

  def test_duplicate_switch_is_rejected_by_default(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {"--flag": "Flag"},
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "duplicate switch"):
      parse_tokens(commands, self.context, ["x", "--flag", "--flag"])

  def test_switch_quantifier_permits_repetition(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--follow": {
            "": "Follow",
            "_quantifier": "*",
          },
        },
      },
    }
    words = ["x", "--follow", "--follow", "--follow"]
    self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))

  def test_static_switch_parameter_alternatives_parse(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--mode": {
            "_params": [
              {"fast": "Fast", "slow": "Slow"},
            ],
          },
        },
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--mode", "fast"]),
      ("x", "--mode", "fast"),
    )
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x", "--mode", "invalid"])

  def test_optional_and_repeated_switch_parameters_parse(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--tag": {
            "_params": [
              {"one": "One", "_quantifier": "?"},
              {"a": "A", "b": "B", "_quantifier": "*"},
            ],
          },
        },
      },
    }
    for words in (
      ["x", "--tag"],
      ["x", "--tag", "one"],
      ["x", "--tag", "one", "a", "b"],
    ):
      self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))

  def test_dynamic_switch_provider_is_authoritative(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": lambda context: {
          "--legal": "Legal",
        },
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--legal"]),
      ("x", "--legal"),
    )
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x", "--other"])

  def test_dynamic_switch_parameter_provider_is_authoritative(self):
    def params(context):
      return {"alpha": "Alpha", "beta": "Beta"}

    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--group": {
            "_params": [
              {"<group>": params},
            ],
          },
        },
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--group", "alpha"]),
      ("x", "--group", "alpha"),
    )

  def test_completion_includes_switches_and_parameter_values(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--mode": {
            "_params": [
              {"fast": "Fast", "slow": "Slow"},
            ],
          },
        },
      },
    }
    self.assertEqual(
      [item.token for item in completion_items(commands, self.context, ["x", "--"])],
      ["--mode"],
    )
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["x", "--mode", ""],
      )],
      ["fast", "slow"],
    )

  def test_repeated_parameter_completion_remains_available(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--tag": {
            "_params": [
              {"a": "A", "b": "B", "_quantifier": "+"},
            ],
          },
        },
      },
    }
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["x", "--tag", "a", ""],
      )],
      ["a", "b"],
    )

  def test_switches_must_be_declared_under_switches(self):
    with self.assertRaisesRegex(CommandGrammarError, "_switches"):
      validate_node({"x": {"--flag": "Flag"}})

  def test_variadic_is_not_a_supported_grammar_item(self):
    with self.assertRaisesRegex(CommandGrammarError, "_variadic"):
      validate_node({"x": {"_variadic": {"min": 1}}})

  def test_public_quantified_commands_parse_real_cli_shapes(self):
    context = Context(Path("."), legal_only=False)
    cases = (
      ["lanes", "select", "5", "6", "--refresh", "--json"],
      ["lanes", "select", "add", "7", "--json"],
      ["lanes", "select", "remove", "8", "--refresh"],
      ["lanes", "list", "A", "--links", "--refresh"],
      ["lanes", "view", "--debug", "A", "--refresh"],
      ["issue", "list", "54", "64", "9", "--links"],
      ["what-next", "--json"],
      ["version", "--json"],
    )
    for words in cases:
      with self.subTest(words=words):
        self.assertEqual(parse_tokens(COMMANDS, context, words), tuple(words))

  def test_public_subcommands_cannot_follow_consumed_values(self):
    context = Context(Path("."), legal_only=False)
    with self.assertRaises(CommandGrammarError):
      parse_tokens(COMMANDS, context, ["lanes", "select", "5", "add", "6"])


if __name__ == "__main__":
  unittest.main()
