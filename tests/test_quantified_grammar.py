from pathlib import Path
import unittest

from repo_workflow.command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  help_lines,
  parse_tokens,
  validate_node,
)

from repo_workflow.public_commands import COMMANDS


class QuantifiedGrammarTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."))

  def issue_values(self, context):
    token = context.current_token
    return {token: "Issue"} if token.isdecimal() else {}

  def lane_values(self, context):
    return {"A": "Lane A", "B": "Lane B"}

  def count_values(self, context):
    return {"1": "One", "2": "Two", "3": "Three"}

  def test_public_simple_completion_provider_returns_string_list(self):
    provider = COMMANDS["lanes"]["select"]["_values"]
    context = Context(Path("."), words=("42",), index=0)
    self.assertEqual(provider(context), ["42"])

  def test_terminal_parameter_accepts_plain_value(self):
    commands = {"show": {"<NAME>": "Name"}}
    self.assertEqual(
      parse_tokens(commands, self.context, ["show", "alpha"]),
      ("show", "alpha"),
    )

  def test_dynamic_terminal_parameter_rejects_unknown_value(self):
    commands = {"show": {"<ISSUE>": self.issue_values}}
    self.assertEqual(
      parse_tokens(commands, self.context, ["show", "42"]),
      ("show", "42"),
    )
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["show", "nope"])

  def test_ordered_sequence_supports_parameter_literal_parameter(self):
    commands = {
      "move": {
        "_ordered": [
          {"<ISSUE>": self.issue_values},
          {"to-lane": "Move to lane"},
          {"<LANE>": self.lane_values},
        ],
      },
    }
    words = ["move", "42", "to-lane", "B"]
    self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))

  def test_ordered_sequence_rejects_wrong_position(self):
    commands = {
      "move": {
        "_ordered": [
          {"<ISSUE>": self.issue_values},
          {"to-lane": "Move to lane"},
          {"<LANE>": self.lane_values},
        ],
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "ordered"):
      parse_tokens(commands, self.context, ["move", "42", "B", "to-lane"])

  def test_ordered_sequence_quantifier_repeats_whole_sequence(self):
    commands = {
      "pair": {
        "_ordered": [
          {"<ISSUE>": self.issue_values},
          {"to-lane": "Move to lane"},
          {"<LANE>": self.lane_values},
        ],
        "_quantifier": "{2}",
      },
    }
    words = [
      "pair", "1", "to-lane", "A",
      "2", "to-lane", "B",
    ]
    self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["pair", "1", "to-lane", "A"])

  def test_parameterized_switch_uses_params_wrapper(self):
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
      parse_tokens(commands, self.context, ["x", "--mode", "other"])

  def test_repeatable_parameterized_switch_preserves_both_quantifiers(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--follow": {
            "_params": [
              {
                "epic": "Epic",
                "feature": "Feature",
                "back-only": "Back only",
              },
              {
                "<N>": self.count_values,
                "_quantifier": "?",
              },
            ],
            "_quantifier": "*",
          },
        },
      },
    }
    words = [
      "x",
      "--follow", "epic", "2",
      "--follow", "back-only",
      "--follow", "feature", "1",
    ]
    self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))

  def test_optional_parameter_cannot_hide_later_required_parameter(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--route": {
            "_params": [
              {"verbose": "Verbose", "_quantifier": "?"},
              {"<LANE>": self.lane_values},
            ],
          },
        },
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "incomplete"):
      parse_tokens(commands, self.context, ["x", "--route"])
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--route", "A"]),
      ("x", "--route", "A"),
    )
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--route", "verbose", "B"]),
      ("x", "--route", "verbose", "B"),
    )

  def test_optional_parameter_completion_includes_later_required_slot(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--route": {
            "_params": [
              {"verbose": "Verbose", "_quantifier": "?"},
              {"<LANE>": self.lane_values},
            ],
          },
        },
      },
    }
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["x", "--route", ""],
      )],
      ["A", "B", "verbose"],
    )

  def test_parameter_position_quantifier_is_independent_of_switch_quantifier(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--tag": {
            "_params": [
              {
                "a": "A",
                "b": "B",
                "_quantifier": "+",
              },
            ],
            "_quantifier": "*",
          },
        },
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--tag", "a", "b"]),
      ("x", "--tag", "a", "b"),
    )
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x", "--tag"])

  def test_switch_is_optional_when_omitted(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--follow": {
            "_params": [{"epic": "Epic"}],
            "_quantifier": "+",
          },
        },
      },
    }
    self.assertEqual(parse_tokens(commands, self.context, ["x"]), ("x",))

  def test_selected_switch_minimum_cardinality_is_enforced(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--flag": {
            "_quantifier": "{2}",
          },
        },
      },
    }
    self.assertEqual(parse_tokens(commands, self.context, ["x"]), ("x",))
    with self.assertRaisesRegex(CommandGrammarError, "occurrences"):
      parse_tokens(commands, self.context, ["x", "--flag"])
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "--flag", "--flag"]),
      ("x", "--flag", "--flag"),
    )

  def test_default_switch_cardinality_rejects_duplicate(self):
    commands = {
      "x": {
        "": "Run",
        "_switches": {
          "--mode": {
            "_params": [{"fast": "Fast"}],
          },
        },
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "duplicate"):
      parse_tokens(
        commands,
        self.context,
        ["x", "--mode", "fast", "--mode", "fast"],
      )

  def test_ordered_completion_tracks_position(self):
    commands = {
      "move": {
        "_ordered": [
          {"<ISSUE>": self.issue_values},
          {"to-lane": "Move to lane"},
          {"<LANE>": self.lane_values},
        ],
      },
    }
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["move", "42", ""],
      )],
      ["to-lane"],
    )
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["move", "42", "to-lane", ""],
      )],
      ["A", "B"],
    )

  def test_help_describes_generic_ordered_parameter(self):
    commands = {
      "move": {
        "_ordered": [
          {"<ISSUE>": "Issue number"},
          {"to-lane": "Move to lane"},
        ],
      },
    }
    self.assertEqual(
      help_lines(commands, self.context, ["move"]),
      ["<ISSUE>  Issue number"],
    )

  def test_all_quantifiers_apply_to_parameter_positions(self):
    cases = {
      "?": (0, 1, 2),
      "*": (0, 3, None),
      "+": (1, 3, None),
      "{2}": (2, 2, 3),
      "{2,}": (2, 4, None),
      "{2,3}": (2, 3, 4),
    }
    for quantifier, (minimum, accepted, too_many) in cases.items():
      commands = {
        "x": {
          "": "Run",
          "_switches": {
            "--p": {
              "_params": [
                {"a": "A", "_quantifier": quantifier},
              ],
            },
          },
        },
      }
      with self.subTest(quantifier=quantifier, accepted=accepted):
        words = ["x", "--p", *(["a"] * accepted)]
        self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))
      if minimum:
        with self.subTest(quantifier=quantifier, too_few=True):
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", "--p", *(["a"] * (minimum - 1))],
            )
      if too_many is not None:
        with self.subTest(quantifier=quantifier, too_many=True):
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", "--p", *(["a"] * too_many)],
            )

  def test_all_quantifiers_apply_to_complete_ordered_sequence(self):
    cases = {
      "?": (0, 1, 2),
      "*": (0, 3, None),
      "+": (1, 3, None),
      "{2}": (2, 2, 3),
      "{2,}": (2, 4, None),
      "{2,3}": (2, 3, 4),
    }
    for quantifier, (minimum, accepted, too_many) in cases.items():
      commands = {
        "x": {
          "_ordered": [{"a": "A"}],
          "_quantifier": quantifier,
        },
      }
      with self.subTest(quantifier=quantifier, accepted=accepted):
        words = ["x", *(["a"] * accepted)]
        self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))
      if minimum:
        with self.subTest(quantifier=quantifier, too_few=True):
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", *(["a"] * (minimum - 1))],
            )
      if too_many is not None:
        with self.subTest(quantifier=quantifier, too_many=True):
          with self.assertRaises(CommandGrammarError):
            parse_tokens(
              commands,
              self.context,
              ["x", *(["a"] * too_many)],
            )

  def test_quantified_command_alternatives_are_unordered_choice_group(self):
    commands = {
      "x": {
        "alpha": "Alpha",
        "beta": "Beta",
        "_quantifier": "+",
      },
    }
    for words in (
      ["x", "alpha"],
      ["x", "beta", "alpha", "beta"],
    ):
      with self.subTest(words=words):
        self.assertEqual(parse_tokens(commands, self.context, words), tuple(words))
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x"])

  def test_quantified_command_alternative_range_is_enforced(self):
    commands = {
      "x": {
        "alpha": "Alpha",
        "beta": "Beta",
        "_quantifier": "{2,3}",
      },
    }
    self.assertEqual(
      parse_tokens(commands, self.context, ["x", "alpha", "beta"]),
      ("x", "alpha", "beta"),
    )
    with self.assertRaises(CommandGrammarError):
      parse_tokens(commands, self.context, ["x", "alpha"])
    with self.assertRaises(CommandGrammarError):
      parse_tokens(
        commands,
        self.context,
        ["x", "alpha", "beta", "alpha", "beta"],
      )

  def test_repeated_nested_choice_requires_ordered_sequence(self):
    with self.assertRaisesRegex(CommandGrammarError, "_ordered"):
      validate_node({
        "x": {
          "alpha": {"next": "Next"},
          "_quantifier": "+",
        },
      })

  def test_choice_completion_remains_available_until_maximum(self):
    commands = {
      "x": {
        "alpha": "Alpha",
        "beta": "Beta",
        "_quantifier": "{1,2}",
      },
    }
    self.assertEqual(
      [item.token for item in completion_items(
        commands,
        self.context,
        ["x", "alpha", ""],
      )],
      ["alpha", "beta"],
    )
    self.assertEqual(
      completion_items(
        commands,
        self.context,
        ["x", "alpha", "beta", ""],
      ),
      [],
    )

  def test_old_bare_switch_parameter_list_is_rejected(self):
    with self.assertRaisesRegex(CommandGrammarError, "_params"):
      validate_node({
        "x": {
          "_switches": {
            "--mode": [{"fast": "Fast"}],
          },
        },
      })


if __name__ == "__main__":
  unittest.main()
