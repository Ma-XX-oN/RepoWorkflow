from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  parse_tokens,
  prefix_valid,
)


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


def _manual_failure(
  commands: dict,
  tokens: tuple[str, ...],
  general: Context,
  legal: Context,
) -> tuple[FailureKind, int] | None:
  for index in range(len(tokens)):
    prefix = tokens[:index + 1]
    if not prefix_valid(commands, general, prefix):
      return FailureKind.UNRECOGNISED, index
    if not prefix_valid(commands, legal, prefix):
      return FailureKind.STATE_INVALID, index

  try:
    parse_tokens(commands, general, tokens)
  except CommandGrammarError:
    return FailureKind.UNRECOGNISED, max(0, len(tokens) - 1)
  try:
    parse_tokens(commands, legal, tokens)
  except CommandGrammarError:
    return FailureKind.STATE_INVALID, max(0, len(tokens) - 1)
  return None


def _completion_failure(
  commands: dict,
  tokens: tuple[str, ...],
  general: Context,
  legal: Context,
) -> tuple[FailureKind, int] | None:
  completed = tokens[:-1]
  for index in range(len(completed)):
    prefix = completed[:index + 1]
    if not prefix_valid(commands, general, prefix):
      return FailureKind.UNRECOGNISED, index
    if not prefix_valid(commands, legal, prefix):
      return FailureKind.STATE_INVALID, index

  general_items = completion_items(commands, general, tokens)
  legal_items = completion_items(commands, legal, tokens)
  if legal_items:
    return None
  if general_items:
    kind = (
      FailureKind.VALUE_NO_COMPLETION
      if any(item.bare_value for item in general_items)
      else FailureKind.STATE_NO_COMPLETION
    )
    return kind, len(tokens) - 1

  all_general = completion_items(commands, general, [*completed, ""])
  if any(item.bare_value for item in all_general):
    return FailureKind.VALUE_NO_COMPLETION, len(tokens) - 1
  if all_general:
    return FailureKind.UNRECOGNISED, len(tokens) - 1
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
  tokens = tuple(words) or ("",)
  result = (
    _completion_failure(commands, tokens, general_context, legal_context)
    if completion
    else _manual_failure(commands, tokens, general_context, legal_context)
  )
  if result is None:
    return None
  kind, index = result
  return CommandFailure(
    kind,
    tokens,
    index,
    state_name,
    tuple(legal_transitions),
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
