from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeAlias

from .command_grammar_support import (
  CommandGrammarError,
  QUANTIFIER,
  SWITCHES,
  consume_switch,
  parse_quantifier,
  slot_candidates,
  switch_description,
  switch_quantifier,
  validate_description,
  validate_switches,
)


LAST_TERMINAL = "<last-terminal>"
TERMINAL = ""
VALUES = "_values"
VALUE_DESCRIPTION = "_value_description"
COMPLETIONS = "completions"
ON_TAB = "on-tab"
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
ValueProvider: TypeAlias = Callable[[Context], object]


@dataclass
class WalkState:
  node: dict
  value_count: int
  switch_counts: dict[str, int]
  pending_slot: dict | None = None
  pending_slot_count: int = 0


def _validate_value_source(value: object, label: str) -> None:
  if not callable(value):
    raise CommandGrammarError(f"{label} must be a callable completion provider")


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


def validate_node(node: object, *, label: str = "COMMANDS") -> None:
  if not isinstance(node, dict):
    raise CommandGrammarError(f"{label} must be a dictionary")
  parse_quantifier(node.get(QUANTIFIER), label=f"{label}[{QUANTIFIER!r}]")
  for token, entry in node.items():
    if not isinstance(token, str):
      raise CommandGrammarError(f"{label} keys must be strings")
    if token == TERMINAL:
      validate_description(entry, f"{label}[{TERMINAL!r}]")
      continue
    if token == VALUES:
      _validate_value_source(entry, f"{label}[{VALUES!r}]")
      continue
    if token == VALUE_DESCRIPTION:
      validate_description(entry, f"{label}[{VALUE_DESCRIPTION!r}]")
      continue
    if token == QUANTIFIER:
      continue
    if token == SWITCHES:
      validate_switches(entry, f"{label}[{SWITCHES!r}]")
      continue
    if token.startswith("_"):
      raise CommandGrammarError(f"{label} contains unsupported special key {token!r}")
    if token.startswith("--"):
      raise CommandGrammarError(
        f"{label} switch {token!r} must be declared under {SWITCHES!r}"
      )
    if token == LAST_TERMINAL:
      raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")
    if isinstance(entry, str):
      validate_description(entry, f"{label}[{token!r}]")
    else:
      validate_node(entry, label=f"{label}[{token!r}]")


def _validate_completion_entries(
  value: object,
  *,
  label: str,
) -> tuple[dict[str, CommandEntry], frozenset[str]]:
  if not isinstance(value, list):
    raise CommandGrammarError(f"{label} must return a list of completions")

  entries: dict[str, CommandEntry] = {}
  values: set[str] = set()
  for index, item in enumerate(value):
    item_label = f"{label}[{index}]"
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
      if token.startswith("_"):
        continue
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
  if isinstance(value, list):
    entries, values = _validate_completion_entries(value, label=label)
    return ResolvedCompletionSpec(entries, values, default_on_tab, context)
  if not isinstance(value, dict):
    raise CommandGrammarError(
      f"{label} must return a completion list or specification dictionary"
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


def completion_spec(node: dict, context: Context) -> ResolvedCompletionSpec:
  source = node.get(VALUES)
  if source is None:
    return ResolvedCompletionSpec({}, frozenset(), default_on_tab, context)
  _validate_value_source(source, VALUES)
  return _validate_completion_spec(source(context), context=context)


def _resolved_switches(node: dict, context: Context) -> dict:
  source = node.get(SWITCHES, {})
  value = source(context) if callable(source) else source
  if not isinstance(value, dict):
    raise CommandGrammarError(f"{SWITCHES} provider must return a dictionary")
  validate_switches(value, SWITCHES)
  return value


def _resolved_node(
  node: dict,
  context: Context,
) -> tuple[dict[str, CommandEntry], frozenset[str], ResolvedCompletionSpec]:
  entries = {
    token: entry
    for token, entry in node.items()
    if token not in {TERMINAL, VALUES, VALUE_DESCRIPTION, QUANTIFIER, SWITCHES}
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


def _walk_prefix(commands: dict, context: Context, words: tuple[str, ...]) -> WalkState:
  node = commands
  value_count = 0
  switch_counts: dict[str, int] = {}
  index = 0
  while index < len(words):
    current = context.at(words, index)
    token = words[index]
    entries, values, _ = _resolved_node(node, current)
    switches = _resolved_switches(node, current)

    if token in switches:
      switch_entry = switches[token]
      quantifier = switch_quantifier(switch_entry)
      count = switch_counts.get(token, 0)
      if quantifier.maximum is not None and count >= quantifier.maximum:
        raise CommandGrammarError(f"duplicate switch is not permitted: {token}")
      switch_counts[token] = count + 1
      index, pending, pending_count = consume_switch(
        switch_entry,
        words,
        index + 1,
        context,
      )
      if pending is not None:
        return WalkState(node, value_count, switch_counts, pending, pending_count)
      continue

    entry = entries.get(token)
    if entry is not None:
      if isinstance(entry, str):
        if index != len(words) - 1:
          raise CommandGrammarError(f"{token!r} is a terminal command")
        return WalkState({TERMINAL: entry}, 0, {})
      node = entry
      value_count = 0
      switch_counts = {}
      index += 1
      continue

    if token in values:
      quantifier = parse_quantifier(
        node.get(QUANTIFIER),
        label=f"{VALUES} {QUANTIFIER}",
      )
      if quantifier.maximum is not None and value_count >= quantifier.maximum:
        raise CommandGrammarError(f"too many values before {token!r}")
      value_count += 1
      index += 1
      continue

    raise CommandGrammarError(f"invalid command token: {token}")

  return WalkState(node, value_count, switch_counts)


def _validate_finished(state: WalkState, context: Context) -> None:
  node = state.node
  if state.pending_slot is not None:
    raise CommandGrammarError("switch parameters are incomplete")
  if VALUES in node:
    quantifier = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
    if state.value_count < quantifier.minimum:
      raise CommandGrammarError("command value arguments are incomplete")
  for token, entry in _resolved_switches(node, context).items():
    quantifier = switch_quantifier(entry)
    if state.switch_counts.get(token, 0) < quantifier.minimum:
      raise CommandGrammarError(f"required switch is missing: {token}")
  if TERMINAL not in node:
    raise CommandGrammarError("command is incomplete")


def prefix_valid(
  commands: dict,
  context: Context,
  tokens: Iterable[str],
) -> bool:
  try:
    _walk_prefix(commands, context, tuple(tokens))
  except CommandGrammarError:
    return False
  return True


def parse_tokens(
  commands: dict,
  context: Context,
  tokens: Iterable[str],
) -> tuple[str, ...]:
  validate_node(commands)
  words = tuple(tokens)
  if not words:
    raise CommandGrammarError("a command is required")
  if LAST_TERMINAL in words:
    raise CommandGrammarError(f"{LAST_TERMINAL} is completion-only")
  state = _walk_prefix(commands, context, words)
  _validate_finished(state, context.at(words, len(words)))
  return words


def _node_items(
  state: WalkState,
  context: Context,
  prefix: str,
  *,
  include_terminal: bool,
) -> tuple[list[Completion], ResolvedCompletionSpec]:
  node = state.node
  entries, values, spec = _resolved_node(node, context)
  result: list[Completion] = []

  if state.pending_slot is not None:
    candidates = slot_candidates(state.pending_slot, context)
    for token, description in candidates.items():
      if token.startswith(prefix):
        result.append(Completion(token, description, True))
    return result, spec

  if include_terminal and TERMINAL in node and LAST_TERMINAL.startswith(prefix):
    result.append(Completion(LAST_TERMINAL, node[TERMINAL]))

  quantifier = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
  can_take_value = (
    VALUES in node
    and (quantifier.maximum is None or state.value_count < quantifier.maximum)
  )
  if (
    include_terminal
    and can_take_value
    and VALUE_DESCRIPTION in node
    and not values
    and "<value>".startswith(prefix)
  ):
    result.append(Completion("<value>", node[VALUE_DESCRIPTION], True))

  for token, entry in entries.items():
    if token.startswith(prefix):
      description = entry if isinstance(entry, str) else entry.get(TERMINAL)
      result.append(Completion(token, description))
  if can_take_value:
    for token in values:
      if token.startswith(prefix):
        result.append(Completion(token, None, True))

  for token, entry in _resolved_switches(node, context).items():
    switch_quantifier = switch_quantifier(entry)
    count = state.switch_counts.get(token, 0)
    if switch_quantifier.maximum is not None and count >= switch_quantifier.maximum:
      continue
    if token.startswith(prefix):
      result.append(Completion(token, switch_description(entry)))

  return result, spec


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
  completed = tuple(tokens[:-1])
  if LAST_TERMINAL in completed:
    return CompletionResponse()

  try:
    state = _walk_prefix(commands, context, completed)
  except CommandGrammarError:
    return CompletionResponse()

  current = context.at(tokens, len(completed))
  result, spec = _node_items(
    state,
    current,
    prefix,
    include_terminal=include_terminal,
  )
  request = CompletionRequest(
    current,
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
  return list(completion_response(
    commands,
    context,
    words,
    include_terminal=include_terminal,
    describe=describe,
  ).items)


def help_lines(
  commands: dict,
  context: Context,
  tokens: Iterable[str] = (),
) -> list[str]:
  response = completion_response(
    commands,
    context,
    [*tokens, ""],
    include_terminal=True,
    describe=True,
  )
  if response.error is not None:
    return [response.error]
  return [
    item.token if item.description is None
    else f"{item.token}  {item.description}"
    for item in response.items
  ]
