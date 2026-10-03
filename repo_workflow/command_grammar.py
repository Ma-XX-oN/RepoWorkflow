from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeAlias


LAST_TERMINAL = "<last-terminal>"
TERMINAL = ""
VALUES = "_values"


class CommandGrammarError(ValueError):
  pass


@dataclass(frozen=True)
class Context:
  root: Path


@dataclass(frozen=True)
class Completion:
  token: str
  description: str | None


CommandEntry: TypeAlias = str | dict
DynamicCommand: TypeAlias = dict[str, CommandEntry]
DynamicResult: TypeAlias = list[str] | list[DynamicCommand]
ValueProvider: TypeAlias = Callable[[Context], DynamicResult]
ValueSource: TypeAlias = list[str] | ValueProvider


def _validate_description(value: object, label: str) -> None:
  if not isinstance(value, str) or not value:
    raise CommandGrammarError(f"{label} must be a non-empty description string")


def _validate_value_source(value: object, label: str) -> None:
  if callable(value):
    return
  if not isinstance(value, list) or not all(
    isinstance(item, str) and item for item in value
  ):
    raise CommandGrammarError(
      f"{label} must be a list of non-empty strings or a callable"
    )


def validate_node(node: object, *, label: str = "COMMANDS") -> None:
  if not isinstance(node, dict):
    raise CommandGrammarError(f"{label} must be a dictionary")
  for token, entry in node.items():
    if not isinstance(token, str):
      raise CommandGrammarError(f"{label} keys must be strings")
    if token == TERMINAL:
      _validate_description(entry, f"{label}[{TERMINAL!r}]")
      continue
    if token == VALUES:
      _validate_value_source(entry, f"{label}[{VALUES!r}]")
      continue
    if not token:
      raise CommandGrammarError(f"{label} contains an invalid empty token")
    if token.startswith("_"):
      raise CommandGrammarError(f"{label} contains unsupported special key {token!r}")
    if token == LAST_TERMINAL:
      raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")
    if isinstance(entry, str):
      _validate_description(entry, f"{label}[{token!r}]")
    else:
      validate_node(entry, label=f"{label}[{token!r}]")


def _validate_dynamic_result(value: object, *, label: str) -> DynamicResult:
  if not isinstance(value, list):
    raise CommandGrammarError(f"{label} must return a list")
  if not value:
    return []
  if all(isinstance(item, str) and item for item in value):
    return list(value)
  if all(isinstance(item, dict) for item in value):
    result: list[DynamicCommand] = []
    for index, item in enumerate(value):
      validate_node(item, label=f"{label}[{index}]")
      forbidden = set(item) & {TERMINAL, VALUES}
      if forbidden:
        raise CommandGrammarError(
          f"{label}[{index}] must contain described next-command tokens only"
        )
      result.append(item)
    return result
  raise CommandGrammarError(
    f"{label} must return either list[str] or list[dict[str, CommandEntry]]"
  )


def _dynamic_entries(node: dict, context: Context) -> tuple[dict[str, CommandEntry], set[str]]:
  source = node.get(VALUES)
  if source is None:
    return {}, set()
  raw = source(context) if callable(source) else source
  value = _validate_dynamic_result(raw, label="_values provider")
  if not value:
    return {}, set()
  if all(isinstance(item, str) for item in value):
    return {}, set(value)
  entries: dict[str, CommandEntry] = {}
  for fragment in value:
    assert isinstance(fragment, dict)
    for token, entry in fragment.items():
      if token in entries or token in node:
        raise CommandGrammarError(f"dynamic command token collides with {token!r}")
      entries[token] = entry
  return entries, set()


def _next_entries(
  node: dict,
  context: Context,
) -> tuple[dict[str, CommandEntry], set[str]]:
  entries = {
    token: entry
    for token, entry in node.items()
    if token not in {TERMINAL, VALUES}
  }
  dynamic_entries, dynamic_values = _dynamic_entries(node, context)
  overlap = set(entries) & set(dynamic_entries)
  if overlap:
    raise CommandGrammarError(
      "dynamic command token collides with static token: " + ", ".join(sorted(overlap))
    )
  entries.update(dynamic_entries)
  return entries, dynamic_values


def parse_tokens(commands: dict, context: Context, tokens: Iterable[str]) -> tuple[str, ...]:
  validate_node(commands)
  words = tuple(tokens)
  if not words:
    raise CommandGrammarError("a command is required")
  if LAST_TERMINAL in words:
    raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")

  node = commands
  for index, token in enumerate(words):
    entries, values = _next_entries(node, context)
    entry = entries.get(token)
    if entry is None:
      if token in values:
        if index != len(words) - 1:
          raise CommandGrammarError(f"{token!r} is a terminal value")
        return words
      raise CommandGrammarError(f"invalid command token: {token}")

    if isinstance(entry, str):
      if index != len(words) - 1:
        raise CommandGrammarError(f"{token!r} is a terminal command")
      return words
    node = entry

  if TERMINAL not in node:
    raise CommandGrammarError("command is incomplete")
  return words


def completion_items(
  commands: dict,
  context: Context,
  words: Iterable[str],
  *,
  include_terminal: bool = False,
) -> list[Completion]:
  validate_node(commands)
  tokens = list(words)
  if not tokens:
    tokens = [""]
  prefix = tokens[-1]
  completed = tokens[:-1]

  node = commands
  for token in completed:
    if token == LAST_TERMINAL:
      return []
    entries, values = _next_entries(node, context)
    entry = entries.get(token)
    if entry is None:
      if token in values:
        return []
      return []
    if isinstance(entry, str):
      return []
    node = entry

  entries, values = _next_entries(node, context)
  result: list[Completion] = []
  if include_terminal and TERMINAL in node and LAST_TERMINAL.startswith(prefix):
    result.append(Completion(LAST_TERMINAL, node[TERMINAL]))

  for token, entry in entries.items():
    if not token.startswith(prefix):
      continue
    description = entry if isinstance(entry, str) else entry.get(TERMINAL)
    result.append(Completion(token, description))
  for token in values:
    if token.startswith(prefix):
      result.append(Completion(token, None))
  return sorted(result, key=lambda item: item.token)


def help_lines(commands: dict, context: Context, tokens: Iterable[str] = ()) -> list[str]:
  validate_node(commands)
  node = commands
  for token in tokens:
    entries, values = _next_entries(node, context)
    if token in values:
      return []
    entry = entries.get(token)
    if entry is None:
      raise CommandGrammarError(f"invalid command token: {token}")
    if isinstance(entry, str):
      return [f"{token}  {entry}"]
    node = entry

  entries, values = _next_entries(node, context)
  items = [
    Completion(token, entry if isinstance(entry, str) else entry.get(TERMINAL))
    for token, entry in entries.items()
  ]
  items.extend(Completion(token, None) for token in values)
  return [
    item.token if item.description is None else f"{item.token}  {item.description}"
    for item in sorted(items, key=lambda item: item.token)
  ]
