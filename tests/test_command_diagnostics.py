from pathlib import Path
import unittest

from repo_workflow.command_diagnostics import (
  FailureKind,
  analyse_failure,
  render_failure,
)
from repo_workflow.command_grammar import Context


class CommandDiagnosticTests(unittest.TestCase):
  def setUp(self):
    self.root = Path(".")

  def general_context(self):
    return Context(self.root, legal_only=False)

  def legal_context(self):
    return Context(self.root, legal_only=True)

  def test_unknown_command_preserves_literal_input_and_underlines_token(self):
    commands = {"validate": {"regression": "Run regression"}}
    failure = analyse_failure(
      commands,
      ["foo"],
      self.general_context(),
      self.legal_context(),
      completion=False,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(failure.kind, FailureKind.UNRECOGNISED)
    self.assertEqual(
      render_failure(failure),
      "RepoWorkflow error: unrecognised command.\n"
      "  foo\n"
      "  ^^^",
    )

  def test_state_invalid_path_underlines_first_invalid_token(self):
    def provider(context):
      if context.legal_only:
        return [{"regression": "Run regression"}]
      return [
        {"regression": "Run regression"},
        {"integration": {
          "succeeded": "Report success",
          "failed": "Report failure",
        }},
      ]

    commands = {"validate": {"_values": provider}}
    failure = analyse_failure(
      commands,
      ["validate", "integration", "s"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(failure.kind, FailureKind.STATE_INVALID)
    self.assertEqual(failure.index, 1)
    self.assertEqual(
      render_failure(failure),
      "RepoWorkflow error: transition is not legal in the current state:\n"
      "  validate integration s\n"
      "           ^^^^^^^^^^^\n"
      "\n"
      "Legal transitions:\n"
      "  regression required\n"
      "  → validate regression",
    )

  def test_state_completion_miss_underlines_literal_partial_token(self):
    def provider(context):
      if context.legal_only:
        return [{"failed": "Report failure"}]
      return [
        {"succeeded": "Report success"},
        {"failed": "Report failure"},
      ]

    commands = {"validate": {"integration": {"_values": provider}}}
    failure = analyse_failure(
      commands,
      ["validate", "integration", "s"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="integration result pending",
      legal_transitions=("validate integration failed",),
    )
    self.assertEqual(failure.kind, FailureKind.STATE_NO_COMPLETION)
    self.assertEqual(failure.index, 2)
    self.assertEqual(
      render_failure(failure),
      "RepoWorkflow error: no completions available from the current state:\n"
      "  validate integration s\n"
      "                       ^\n"
      "\n"
      "Legal transitions:\n"
      "  integration result pending\n"
      "  → validate integration failed",
    )

  def test_bare_value_completion_miss_has_no_transition_block(self):
    commands = {
      "validate": {
        "regression": {
          "--group": {
            "_values": ["alpha", "beta"],
          },
        },
      },
    }
    failure = analyse_failure(
      commands,
      ["validate", "regression", "--group", "z"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(failure.kind, FailureKind.VALUE_NO_COMPLETION)
    rendered = render_failure(failure)
    self.assertEqual(
      rendered,
      "RepoWorkflow error: no completions available for:\n"
      "  validate regression --group z\n"
      "                              ^",
    )
    self.assertNotIn("Legal transitions:", rendered)

  def test_callable_bare_value_miss_uses_same_generic_diagnostic(self):
    commands = {
      "validate": {
        "regression": {
          "--group": {
            "_values": lambda context: ["alpha", "beta"],
          },
        },
      },
    }
    failure = analyse_failure(
      commands,
      ["validate", "regression", "--group", "z"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(failure.kind, FailureKind.VALUE_NO_COMPLETION)
    self.assertNotIn("Legal transitions:", render_failure(failure))

  def test_descendants_do_not_duplicate_first_state_failure(self):
    def provider(context):
      if context.legal_only:
        return [{"regression": "Run regression"}]
      return [{
        "integration": {
          "succeeded": "Report success",
          "stopped": "Report stopped",
          "skipped": "Report skipped",
        },
      }]

    commands = {"validate": {"_values": provider}}
    failure = analyse_failure(
      commands,
      ["validate", "integration", "s"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(failure.index, 1)
    self.assertEqual(render_failure(failure).count("RepoWorkflow error:"), 1)
    self.assertEqual(render_failure(failure).count("Legal transitions:"), 1)

  def test_manual_and_completion_share_first_state_mismatch(self):
    def provider(context):
      if context.legal_only:
        return [{"regression": "Run regression"}]
      return [
        {"regression": "Run regression"},
        {"integration": {"succeeded": "Report success"}},
      ]

    commands = {"validate": {"_values": provider}}
    manual = analyse_failure(
      commands,
      ["validate", "integration", "succeeded"],
      self.general_context(),
      self.legal_context(),
      completion=False,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    completion = analyse_failure(
      commands,
      ["validate", "integration", "s"],
      self.general_context(),
      self.legal_context(),
      completion=True,
      state_name="regression required",
      legal_transitions=("validate regression",),
    )
    self.assertEqual(manual.kind, FailureKind.STATE_INVALID)
    self.assertEqual(completion.kind, FailureKind.STATE_INVALID)
    self.assertEqual(manual.index, completion.index)

  def test_state_display_is_human_readable(self):
    commands = {"validate": {"_values": lambda context: [] if context.legal_only else [{"regression": "Run"}]}}
    failure = analyse_failure(
      commands,
      ["validate", "regression"],
      self.general_context(),
      self.legal_context(),
      completion=False,
      state_name="integration result pending",
      legal_transitions=("validate integration failed",),
    )
    rendered = render_failure(failure)
    self.assertIn("  integration result pending", rendered)
    self.assertNotIn("integration-result-pending", rendered)


if __name__ == "__main__":
  unittest.main()
