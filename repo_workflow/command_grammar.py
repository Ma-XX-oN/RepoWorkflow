from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeAlias


LAST_TERMINAL = "<last-terminal>"
TERMINAL = ""
VALUES = "_values"
COMPLETIONS = "completions"
ON_TAB = "on-tab"
VARIADIC = "_variadic"


class CommandGrammarError(ValueError):
  pass


@dataclass(frozen=True)
class Context:
  root: Path
  legal_only: bool = True
  words: tuple[str, ...] = ()
  index: int = 0

  def at(self, words: Iterable[str], index: int) -> "Context":
    return Context(self.root, self.legal_only, tuple(words), index)

  @property
  def current_token(self) -> str:
    if 0 <= self.index < len(self.words):
      return self.words[self.index]
    return ""


@dataclass(frozen=True)
class Completion:
  token: str
  description: str | None
  bare_value: bool = False


@dataclass(frozen=True)
class CompletionResponse:
  items: tuple[Completion, ...] = ()
  error: str | None = None
  append_space: bool = True


@dataclass(frozen=True)
class CompletionRequest:
  context: Context
  prefix: str
  items: tuple[Completion, ...]
  describe: bool = False

  def default(self, *, append_space: bool = True) -> CompletionResponse:
    return CompletionResponse(self.items, append_space=append_space)

  def error(self, message: str) -> CompletionResponse:
    return CompletionResponse(error=message)


CompletionHandler: TypeAlias = Callable[[CompletionRequest], CompletionResponse]
CommandEntry: TypeAlias = str | dict
DynamicCommand: TypeAlias = dict[str, CommandEntry]
CompletionEntry: TypeAlias = str | DynamicCommand
ValueProvider: TypeAlias = Callable[[Context], dict]


def default_on_tab(request: CompletionRequest) -> CompletionResponse:
  return request.default()


@dataclass(frozen=True)
class ResolvedCompletionSpec:
  entries: dict[str, CommandEntry]
  values: frozenset[str]
  on_tab: CompletionHandler
  context: Context

  def _items(self, prefix: str) -> tuple[Completion, ...]:
    result: list[Completion] = []
    for token, entry in self.entries.items():
      if token.startswith(prefix):
        description = entry if isinstance(entry, str) else entry.get(TERMINAL)
        result.append(Completion(token, description))
    for token in self.values:
      if token.startswith(prefix):
        result.append(Completion(token, None, True))
    return tuple(sorted(result, key=lambda item: item.token))

  def request(
    self,
    *,
    prefix: str,
    describe: bool,
  ) -> CompletionRequest:
    return CompletionRequest(
      self.context,
      prefix,
      self._items(prefix),
      describe,
    )


def _validate_description(value: object, label: str) -> None:
  if not isinstance(value, str) or not value:
    raise CommandGrammarError(f"{label} must be a non-empty description string")


def _validate_value_source(value: object, label: str) -> None:
  if not callable(value):
    raise CommandGrammarError(f"{label} must be a callable completion provider")


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
    if token == VARIADIC:
      if not isinstance(entry, dict) or set(entry) != {"min", "description"}:
        raise CommandGrammarError(f"{label}[{VARIADIC!r}] must define min and description")
      if isinstance(entry["min"], bool) or not isinstance(entry["min"], int) or entry["min"] < 0:
        raise CommandGrammarError(f"{label}[{VARIADIC!r}].min must be non-negative")
      _validate_description(entry["description"], f"{label}[{VARIADIC!r}].description")
      continue
    if token.startswith("_"):
      raise CommandGrammarError(f"{label} contains unsupported special key {token!r}")
    if token == LAST_TERMINAL:
      raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")
    if isinstance(entry, str):
      _validate_description(entry, f"{label}[{token!r}]")
    else:
      validate_node(entry, label=f"{label}[{token!r}]")


def _validate_completion_entries(
  value: object,
  *,
  label: str,
) -> tuple[dict[str, CommandEntry], frozenset[str]]:
  if not isinstance(value, list):
    raise CommandGrammarError(f"{label}[{COMPLETIONS!r}] must be a list")

  entries: dict[str, CommandEntry] = {}
  values: set[str] = set()
  for index, item in enumerate(value):
    item_label = f"{label}[{COMPLETIONS!r}][{index}]"
    if isinstance(item, str):
      if not item:
        raise CommandGrammarError(f"{item_label} must not be empty")
      if item in values or item in entries:
        raise CommandGrammarError(f"dynamic command token collides with {item!r}")
      values.add(item)
      continue
    if not isinstance(item, dict):
      raise CommandGrammarError(
        f"{item_label} must be a non-empty string or described command fragment"
      )
    validate_node(item, label=item_label)
    if set(item) & {TERMINAL, VALUES}:
      raise CommandGrammarError(
        f"{item_label} must contain described next-command tokens only"
      )
    for token, entry in item.items():
      if token in entries or token in values:
        raise CommandGrammarError(f"dynamic command token collides with {token!r}")
      entries[token] = entry
  return entries, frozenset(values)


def _validate_completion_spec(
  value: object,
  *,
  context: Context,
  label: str = "_values provider",
) -> ResolvedCompletionSpec:
  if not isinstance(value, dict):
    raise CommandGrammarError(
      f"{label} must return a completion specification dictionary"
    )
  unknown = set(value) - {COMPLETIONS, ON_TAB}
  if unknown:
    names = ", ".join(repr(name) for name in sorted(unknown))
    raise CommandGrammarError(f"{label} contains unsupported field(s): {names}")
  if COMPLETIONS not in value:
    raise CommandGrammarError(f"{label} must define {COMPLETIONS!r}")

  entries, values = _validate_completion_entries(value[COMPLETIONS], label=label)
  handler = value.get(ON_TAB, default_on_tab)
  if not callable(handler):
    raise CommandGrammarError(f"{label}[{ON_TAB!r}] must be callable")
  return ResolvedCompletionSpec(entries, values, handler, context)


def completion_spec(
  node: dict,
  context: Context,
) -> ResolvedCompletionSpec:
  source = node.get(VALUES)
  if source is None:
    return ResolvedCompletionSpec({}, frozenset(), default_on_tab, context)
  _validate_value_source(source, VALUES)
  return _validate_completion_spec(source(context), context=context)


def _resolved_node(
  node: dict,
  context: Context,
) -> tuple[
  dict[str, CommandEntry],
  frozenset[str],
  ResolvedCompletionSpec,
]:
  entries = {
    token: entry
    for token, entry in node.items()
    if token not in {TERMINAL, VALUES, VARIADIC}
  }
  spec = completion_spec(node, context)
  overlap = set(entries) & set(spec.entries)
  if overlap:
    raise CommandGrammarError(
      "dynamic command token collides with static token: " + ", ".join(sorted(overlap))
    )
  entries.update(spec.entries)
  return entries, spec.values, spec


def next_entries(
  node: dict,
  context: Context,
) -> tuple[dict[str, CommandEntry], set[str]]:
  entries, values, _ = _resolved_node(node, context)
  return entries, set(values)


def parse_tokens(commands: dict, context: Context, tokens: Iterable[str]) -> tuple[str, ...]:
  validate_node(commands)
  words = tuple(tokens)
  if not words:
    raise CommandGrammarError("a command is required")
  if LAST_TERMINAL in words:
    raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")

  node = commands
  for index, token in enumerate(words):
    entries, values = next_entries(node, context.at(words, index))
    entry = entries.get(token)
    if entry is None:
      variadic = node.get(VARIADIC)
      if variadic is not None:
        remaining = len(words) - index
        if remaining < variadic["min"]:
          raise CommandGrammarError("variadic command tail is incomplete")
        return words
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


def completion_response(
  commands: dict,
  context: Context,
  words: Iterable[str],
  *,
  include_terminal: bool = False,
  describe: bool = False,
) -> CompletionResponse:
  validate_node(commands)
  tokens = list(words)
  if not tokens:
    tokens = [""]
  prefix = tokens[-1]
  completed = tokens[:-1]

  node = commands
  for index, token in enumerate(completed):
    if token == LAST_TERMINAL:
      return CompletionResponse()
    entries, values = next_entries(node, context.at(tokens, index))
    entry = entries.get(token)
    if entry is None or token in values or isinstance(entry, str):
      return CompletionResponse()
    node = entry

  entries, values, spec = _resolved_node(
    node,
    context.at(tokens, len(completed)),
  )
  result: list[Completion] = []
  if (
    include_terminal
    and TERMINAL in node
    and (entries or values)
    and LAST_TERMINAL.startswith(prefix)
  ):
    result.append(Completion(LAST_TERMINAL, node[TERMINAL]))

  for token, entry in entries.items():
    if token.startswith(prefix):
      description = entry if isinstance(entry, str) else entry.get(TERMINAL)
      result.append(Completion(token, description))
  for token in values:
    if token.startswith(prefix):
      result.append(Completion(token, None, True))

  request = CompletionRequest(
    context.at(tokens, len(completed)),
    prefix,
    tuple(sorted(result, key=lambda item: item.token)),
    describe,
  )
  response = spec.on_tab(request)
  if not isinstance(response, CompletionResponse):
    raise CommandGrammarError("on-tab handler must return CompletionResponse")
  return response


def completion_items(
  commands: dict,
  context: Context,
  words: Iterable[str],
  *,
  include_terminal: bool = False,
  describe: bool = False,
) -> list[Completion]:
  response = completion_response(
    commands,
    context,
    words,
    include_terminal=include_terminal,
    describe=describe,
  )
  return list(response.items)


def help_lines(commands: dict, context: Context, tokens: Iterable[str] = ()) -> list[str]:
  validate_node(commands)
  words = list(tokens)
  response = completion_response(
    commands,
    context,
    [*words, ""],
    include_terminal=True,
    describe=True,
  )
  if response.error is not None:
    return [response.error]
  return [
    item.token if item.description is None else f"{item.token}  {item.description}"
    for item in response.items
  ]
