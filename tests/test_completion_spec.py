from pathlib import Path
import unittest

from repo_workflow.command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  completion_spec,
  help_lines,
  validate_node,
)


class CompletionSpecificationTests(unittest.TestCase):
  def setUp(self):
    self.context = Context(Path("."))

  def test_values_must_be_provider_not_literal_list(self):
    with self.assertRaisesRegex(CommandGrammarError, "callable"):
      validate_node({"group": {"_values": ["one", "two"]}})

  def test_provider_must_return_explicit_completion_spec(self):
    commands = {"group": {"_values": lambda context: ["one", "two"]}}
    with self.assertRaisesRegex(CommandGrammarError, "completion specification"):
      completion_items(commands, self.context, ["group", ""])

  def test_completion_spec_requires_completions(self):
    commands = {"group": {"_values": lambda context: {}}}
    with self.assertRaisesRegex(CommandGrammarError, "completions"):
      completion_items(commands, self.context, ["group", ""])

  def test_completion_spec_rejects_unknown_fields(self):
    commands = {
      "group": {
        "_values": lambda context: {
          "completions": ["one"],
          "mystery": True,
        },
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "mystery"):
      completion_items(commands, self.context, ["group", ""])

  def test_on_tab_must_be_callable(self):
    commands = {
      "group": {
        "_values": lambda context: {
          "completions": ["one"],
          "on-tab": "not callable",
        },
      },
    }
    with self.assertRaisesRegex(CommandGrammarError, "on-tab"):
      completion_items(commands, self.context, ["group", ""])

  def test_default_handler_is_used_when_on_tab_is_absent(self):
    commands = {
      "group": {
        "_values": lambda context: {
          "completions": ["alpha", "beta"],
        },
      },
    }
    spec = completion_spec(commands["group"], self.context)
    self.assertIsNotNone(spec.on_tab)
    self.assertEqual(
      [item.token for item in completion_items(commands, self.context, ["group", ""])],
      ["alpha", "beta"],
    )

  def test_custom_on_tab_is_first_class_and_receives_filtered_candidates(self):
    seen = []

    def handler(request):
      seen.append((
        request.prefix,
        tuple(item.token for item in request.items),
        request.describe,
      ))
      return request.default()

    commands = {
      "group": {
        "_values": lambda context: {
          "completions": ["alpha", "beta"],
          "on-tab": handler,
        },
      },
    }
    items = completion_items(commands, self.context, ["group", "a"])
    self.assertEqual([item.token for item in items], ["alpha"])
    self.assertEqual(seen, [("a", ("alpha",), False)])

  def test_custom_handler_can_return_contextual_error(self):
    def handler(request):
      return request.error("No issue-scoped test group exists.")

    commands = {
      "group": {
        "_values": lambda context: {
          "completions": [],
          "on-tab": handler,
        },
      },
    }
    result = completion_items(commands, self.context, ["group", ""])
    self.assertEqual(result, [])
    spec = completion_spec(commands["group"], self.context)
    response = spec.on_tab(spec.request(prefix="", describe=False))
    self.assertEqual(response.error, "No issue-scoped test group exists.")

  def test_described_dynamic_fragments_still_preserve_descriptions(self):
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
    items = completion_items(commands, self.context, ["validate", ""])
    self.assertEqual(
      [(item.token, item.description) for item in items],
      [("integration", None), ("regression", "Run regression")],
    )

  def test_empty_completion_spec_is_valid(self):
    commands = {
      "group": {
        "_values": lambda context: {
          "completions": [],
        },
      },
    }
    self.assertEqual(
      completion_items(commands, self.context, ["group", ""]),
      [],
    )

  def test_help_uses_same_dynamic_descriptions_as_detailed_completion(self):
    commands = {
      "validate": {
        "_values": lambda context: {
          "completions": [
            {"failed": "Report failure"},
            {"succeeded": "Report success"},
          ],
        },
      },
    }
    detailed = [
      item.token if item.description is None
      else f"{item.token}  {item.description}"
      for item in completion_items(commands, self.context, ["validate", ""])
    ]
    self.assertEqual(help_lines(commands, self.context, ["validate"]), detailed)


if __name__ == "__main__":
  unittest.main()
