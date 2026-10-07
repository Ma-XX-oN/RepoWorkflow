from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeAlias

from .command_grammar_support import (
  CommandGrammarError,
  ORDERED,
  PARAMS,
  QUANTIFIER,
  SWITCHES,
  consume_switch,
  is_parameter,
  ordered_match,
  parse_quantifier,
  slot_candidates,
  switch_description,
  switch_quantifier,
  validate_description,
  validate_ordered,
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
CommandEntry: TypeAlias = str | dict | Callable
DynamicCommand: TypeAlias = dict[str, CommandEntry]
ValueProvider: TypeAlias = Callable[[Context], object]


@dataclass
class WalkState:
  node: dict
  value_count: int
  switch_counts: dict[str, int]
  pending_slot: dict | None = None
  pending_slot_count: int = 0
  ordered_index: int = 0
  ordered_count: int = 0


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
        description = entry if isinstance(entry, str) else None
        result.append(Completion(token, description))
    for token in self.values:
      if token.startswith(prefix):
        result.append(Completion(token, None, True))
    return tuple(sorted(result, key=lambda item: item.token))

  def request(self, *, prefix: str, describe: bool) -> CompletionRequest:
    return CompletionRequest(self.context, prefix, self._items(prefix), describe)


def validate_node(node: object, *, label: str = "COMMANDS") -> None:
  if not isinstance(node, dict):
    raise CommandGrammarError(f"{label} must be a dictionary")
  parse_quantifier(node.get(QUANTIFIER), label=f"{label}[{QUANTIFIER!r}]")
  if ORDERED in node:
    validate_ordered(node[ORDERED], f"{label}[{ORDERED!r}]")
    if VALUES in node:
      raise CommandGrammarError(f"{label} cannot combine {ORDERED!r} and {VALUES!r}")
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
    if token in {QUANTIFIER, ORDERED}:
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
    if is_parameter(token):
      if callable(entry):
        continue
      validate_description(entry, f"{label}[{token!r}]")
      continue
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
  specials = {TERMINAL, VALUES, VALUE_DESCRIPTION, QUANTIFIER, SWITCHES, ORDERED}
  entries = {token: entry for token, entry in node.items() if token not in specials}
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


def _parameter_match(entries: dict, token: str, context: Context):
  for name, entry in entries.items():
    if not is_parameter(name):
      continue
    if callable(entry):
      values = entry(context)
      if not isinstance(values, dict):
        raise CommandGrammarError("parameter completion provider must return a dictionary")
      if token in values:
        return entry
    elif token and not token.startswith("--"):
      return entry
  return None


def _consume_switch_token(
  node: dict,
  words: tuple[str, ...],
  index: int,
  context: Context,
  switch_counts: dict[str, int],
) -> tuple[int, dict | None, int] | None:
  current = context.at(words, index)
  switches = _resolved_switches(node, current)
  token = words[index]
  if token not in switches:
    return None
  entry = switches[token]
  bounds = switch_quantifier(entry)
  count = switch_counts.get(token, 0)
  if bounds.maximum is not None and count >= bounds.maximum:
    raise CommandGrammarError(f"duplicate switch is not permitted: {token}")
  switch_counts[token] = count + 1
  return consume_switch(entry, words, index + 1, context)


def _walk_ordered(
  node: dict,
  context: Context,
  words: tuple[str, ...],
  index: int,
  state: WalkState,
) -> tuple[int, WalkState]:
  ordered = node[ORDERED]
  bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{ORDERED} {QUANTIFIER}")
  while index < len(words):
    switched = _consume_switch_token(
      node,
      words,
      index,
      context,
      state.switch_counts,
    )
    if switched is not None:
      index, pending, pending_count = switched
      if pending is not None:
        state.pending_slot = pending
        state.pending_slot_count = pending_count
        return index, state
      continue
    if bounds.maximum is not None and state.ordered_count >= bounds.maximum:
      raise CommandGrammarError("too many ordered command sequences")
    slot = ordered[state.ordered_index]
    current = context.at(words, index)
    if not ordered_match(slot, words[index], current):
      raise CommandGrammarError(f"invalid ordered command token: {words[index]}")
    state.ordered_index += 1
    index += 1
    if state.ordered_index == len(ordered):
      state.ordered_index = 0
      state.ordered_count += 1
  return index, state


def _walk_prefix(commands: dict, context: Context, words: tuple[str, ...]) -> WalkState:
  node = commands
  state = WalkState(node, 0, {})
  index = 0
  while index < len(words):
    state.node = node
    if ORDERED in node:
      index, state = _walk_ordered(node, context, words, index, state)
      break
    switched = _consume_switch_token(
      node,
      words,
      index,
      context,
      state.switch_counts,
    )
    if switched is not None:
      index, pending, pending_count = switched
      if pending is not None:
        state.pending_slot = pending
        state.pending_slot_count = pending_count
        return state
      continue
    current = context.at(words, index)
    token = words[index]
    entries, values, _ = _resolved_node(node, current)
    entry = entries.get(token) if state.value_count == 0 else None
    if entry is None and state.value_count == 0:
      entry = _parameter_match(entries, token, current)
    if entry is not None:
      if isinstance(entry, str) or callable(entry):
        if index != len(words) - 1:
          raise CommandGrammarError(f"{token!r} is a terminal command")
        return WalkState({TERMINAL: "Parameter"}, 0, {})
      node = entry
      state = WalkState(node, 0, {})
      index += 1
      continue
    if token in values:
      bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
      if bounds.maximum is not None and state.value_count >= bounds.maximum:
        raise CommandGrammarError(f"too many values before {token!r}")
      state.value_count += 1
      index += 1
      continue
    if VALUES in node and state.value_count:
      bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
      if bounds.maximum is not None and state.value_count >= bounds.maximum:
        raise CommandGrammarError(f"{words[index - 1]!r} is a terminal value")
    raise CommandGrammarError(f"invalid command token: {token}")
  state.node = node
  return state


def _validate_finished(state: WalkState, context: Context) -> None:
  node = state.node
  if state.pending_slot is not None:
    bounds = parse_quantifier(
      state.pending_slot.get(QUANTIFIER),
      label="parameter quantifier",
    )
    if state.pending_slot_count < bounds.minimum:
      raise CommandGrammarError("switch parameters are incomplete")
  if ORDERED in node:
    bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{ORDERED} {QUANTIFIER}")
    if state.ordered_index or state.ordered_count < bounds.minimum:
      raise CommandGrammarError("ordered command arguments are incomplete")
    return
  if VALUES in node:
    bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
    if state.value_count < bounds.minimum:
      raise CommandGrammarError("command value arguments are incomplete")
    return
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


def _entry_items(
  entries: dict[str, CommandEntry],
  context: Context,
  prefix: str,
  *,
  describe: bool,
) -> list[Completion]:
  result: list[Completion] = []
  for token, entry in entries.items():
    if is_parameter(token):
      slot = {token: entry}
      for value, description in slot_candidates(
        slot,
        context,
        describe_generic=describe,
      ).items():
        if value.startswith(prefix):
          result.append(Completion(value, description, True))
      continue
    if token.startswith(prefix):
      description = entry if isinstance(entry, str) else None
      result.append(Completion(token, description))
  return result


def _switch_items(
  node: dict,
  state: WalkState,
  context: Context,
  prefix: str,
) -> list[Completion]:
  result: list[Completion] = []
  for token, entry in _resolved_switches(node, context).items():
    bounds = switch_quantifier(entry)
    count = state.switch_counts.get(token, 0)
    if bounds.maximum is not None and count >= bounds.maximum:
      continue
    if token.startswith(prefix):
      result.append(Completion(token, switch_description(entry)))
  return result


def _node_items(
  state: WalkState,
  context: Context,
  prefix: str,
  *,
  include_terminal: bool,
  describe: bool,
) -> tuple[list[Completion], ResolvedCompletionSpec]:
  node = state.node
  entries, values, spec = _resolved_node(node, context)
  result: list[Completion] = []
  if state.pending_slot is not None:
    for token, description in slot_candidates(
      state.pending_slot,
      context,
      describe_generic=describe,
    ).items():
      if token.startswith(prefix):
        result.append(Completion(token, description, True))
    bounds = parse_quantifier(
      state.pending_slot.get(QUANTIFIER),
      label="parameter quantifier",
    )
    if state.pending_slot_count < bounds.minimum:
      return result, spec
  if ORDERED in node:
    bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{ORDERED} {QUANTIFIER}")
    if bounds.maximum is None or state.ordered_count < bounds.maximum:
      slot = node[ORDERED][state.ordered_index]
      for token, description in slot_candidates(
        slot,
        context,
        describe_generic=describe,
      ).items():
        if token.startswith(prefix):
          result.append(Completion(token, description, True))
    result.extend(_switch_items(node, state, context, prefix))
    return result, spec
  if include_terminal and TERMINAL in node and LAST_TERMINAL.startswith(prefix):
    result.append(Completion(LAST_TERMINAL, node[TERMINAL]))
  bounds = parse_quantifier(node.get(QUANTIFIER), label=f"{VALUES} {QUANTIFIER}")
  can_take_value = (
    VALUES in node
    and (bounds.maximum is None or state.value_count < bounds.maximum)
  )
  if (
    include_terminal
    and can_take_value
    and VALUE_DESCRIPTION in node
    and not values
    and "<value>".startswith(prefix)
  ):
    result.append(Completion("<value>", node[VALUE_DESCRIPTION], True))
  if state.value_count == 0:
    result.extend(_entry_items(entries, context, prefix, describe=describe))
  if can_take_value:
    for token in values:
      if token.startswith(prefix):
        result.append(Completion(token, None, True))
  result.extend(_switch_items(node, state, context, prefix))
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
  tokens = list(words) or [""]
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
    describe=describe,
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
