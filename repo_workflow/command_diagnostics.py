from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .command_grammar import Context, TERMINAL, next_entries


class FailureKind(str, Enum):
  UNRECOGNISED = "unrecognised"
  STATE_INVALID = "state-invalid"
  STATE_NO_COMPLETION = "state-no-completion"
  VALUE_NO_COMPLETION = "value-no-completion"


@dataclass(frozen=True)
class CommandFailure:
  kind: FailureKind
  words: tuple[str, ...]
  index: int
  state_name: str | None = None
  legal_transitions: tuple[str, ...] = ()


def _entry_for(
  node: dict,
  context: Context,
  words: tuple[str, ...],
  index: int,
  token: str,
):
  entries, values = next_entries(node, context.at(words, index))
  return entries.get(token), values


def _advance(node: dict, entry):
  if isinstance(entry, dict):
    return entry
  return None


def analyse_failure(
  commands: dict,
  words: Iterable[str],
  general_context: Context,
  legal_context: Context,
  *,
  completion: bool,
  state_name: str | None,
  legal_transitions: Iterable[str],
) -> CommandFailure | None:
  tokens = tuple(words)
  transitions = tuple(legal_transitions)
  if not tokens:
    tokens = ("",)

  last_index = len(tokens) - 1
  exact_count = last_index if completion else len(tokens)
  general_node = commands
  legal_node = commands

  for index in range(exact_count):
    token = tokens[index]
    general_entry, general_values = _entry_for(
      general_node,
      general_context,
      tokens,
      index,
      token,
    )
    legal_entry, legal_values = _entry_for(
      legal_node,
      legal_context,
      tokens,
      index,
      token,
    )

    general_known = general_entry is not None or token in general_values
    legal_known = legal_entry is not None or token in legal_values

    if not general_known:
      return CommandFailure(
        FailureKind.UNRECOGNISED,
        tokens,
        index,
        state_name,
        transitions,
      )
    if not legal_known:
      return CommandFailure(
        FailureKind.STATE_INVALID,
        tokens,
        index,
        state_name,
        transitions,
      )

    if token in general_values or token in legal_values:
      if index != exact_count - 1:
        return CommandFailure(
          FailureKind.UNRECOGNISED,
          tokens,
          index + 1,
          state_name,
          transitions,
        )
      return None

    general_node = _advance(general_node, general_entry)
    legal_node = _advance(legal_node, legal_entry)
    if general_node is None or legal_node is None:
      if index != exact_count - 1:
        return CommandFailure(
          FailureKind.UNRECOGNISED,
          tokens,
          index + 1,
          state_name,
          transitions,
        )
      return None

  if not completion:
    if isinstance(general_node, dict) and TERMINAL not in general_node:
      return CommandFailure(
        FailureKind.UNRECOGNISED,
        tokens,
        max(0, len(tokens) - 1),
        state_name,
        transitions,
      )
    if isinstance(legal_node, dict) and TERMINAL not in legal_node:
      return CommandFailure(
        FailureKind.STATE_INVALID,
        tokens,
        max(0, len(tokens) - 1),
        state_name,
        transitions,
      )
    return None

  partial = tokens[-1]
  index = last_index
  general_entries, general_values = next_entries(
    general_node,
    general_context.at(tokens, index),
  )
  legal_entries, legal_values = next_entries(
    legal_node,
    legal_context.at(tokens, index),
  )

  general_matches = {
    token for token in general_entries if token.startswith(partial)
  }
  general_value_matches = {
    token for token in general_values if token.startswith(partial)
  }
  legal_matches = {
    token for token in legal_entries if token.startswith(partial)
  }
  legal_value_matches = {
    token for token in legal_values if token.startswith(partial)
  }

  if legal_matches or legal_value_matches:
    return None

  if general_value_matches or general_values:
    return CommandFailure(
      FailureKind.VALUE_NO_COMPLETION,
      tokens,
      index,
      state_name,
      transitions,
    )

  if general_matches:
    return CommandFailure(
      FailureKind.STATE_NO_COMPLETION,
      tokens,
      index,
      state_name,
      transitions,
    )

  return CommandFailure(
    FailureKind.UNRECOGNISED,
    tokens,
    index,
    state_name,
    transitions,
  )


def _underline(words: tuple[str, ...], index: int) -> str:
  before = sum(len(word) + 1 for word in words[:index])
  width = max(1, len(words[index]))
  return "  " + (" " * before) + ("^" * width)


def _with_transitions(lines: list[str], failure: CommandFailure) -> list[str]:
  if failure.kind == FailureKind.VALUE_NO_COMPLETION:
    return lines
  if failure.state_name is None:
    return lines

  lines.extend(["", "Legal transitions:", f"  {failure.state_name}"])
  if failure.legal_transitions:
    lines.extend(f"  → {transition}" for transition in failure.legal_transitions)
  else:
    lines.append("  (none)")
  return lines


def render_failure(failure: CommandFailure) -> str:
  if failure.kind == FailureKind.UNRECOGNISED:
    header = "RepoWorkflow error: unrecognised command."
  elif failure.kind == FailureKind.STATE_INVALID:
    header = "RepoWorkflow error: transition is not legal in the current state:"
  elif failure.kind == FailureKind.STATE_NO_COMPLETION:
    header = "RepoWorkflow error: no completions available from the current state:"
  else:
    header = "RepoWorkflow error: no completions available for:"

  lines = [
    header,
    "  " + " ".join(failure.words),
    _underline(failure.words, failure.index),
  ]
  return "\n".join(_with_transitions(lines, failure))
