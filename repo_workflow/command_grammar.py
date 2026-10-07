from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .command_grammar_spec import (
  COMPLETIONS,
  LAST_TERMINAL,
  ON_TAB,
  TERMINAL,
  VALUE_DESCRIPTION,
  VALUES,
  CommandEntry,
  Completion,
  CompletionRequest,
  CompletionResponse,
  Context,
  ResolvedCompletionSpec,
  completion_spec,
  next_entries,
  resolved_node,
  resolved_switches,
  validate_node,
)
from .command_grammar_support import (
  CommandGrammarError,
  ORDERED,
  QUANTIFIER,
  consume_switch,
  is_parameter,
  ordered_match,
  parse_quantifier,
  slot_candidates,
  switch_description,
  switch_quantifier,
)


@dataclass
class WalkState:
  node: dict
  value_count: int
  switch_counts: dict[str, int]
  pending_slot: dict | None = None
  pending_slot_count: int = 0
  ordered_index: int = 0
  ordered_count: int = 0


def _parameter_match(entries: dict, token: str, context: Context):
  for name, entry in entries.items():
    if not is_parameter(name):
      continue
    if callable(entry):
      values = entry(context)
      if not isinstance(values, dict):
        raise CommandGrammarError(
          "parameter completion provider must return a dictionary"
        )
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
  switches = resolved_switches(node, current)
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
  bounds = parse_quantifier(
    node.get(QUANTIFIER),
    label=f"{ORDERED} {QUANTIFIER}",
  )
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
    entries, values, _ = resolved_node(node, current)
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
      bounds = parse_quantifier(
        node.get(QUANTIFIER),
        label=f"{VALUES} {QUANTIFIER}",
      )
      if bounds.maximum is not None and state.value_count >= bounds.maximum:
        raise CommandGrammarError(f"too many values before {token!r}")
      state.value_count += 1
      index += 1
      continue
    if VALUES in node and state.value_count:
      bounds = parse_quantifier(
        node.get(QUANTIFIER),
        label=f"{VALUES} {QUANTIFIER}",
      )
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
    bounds = parse_quantifier(
      node.get(QUANTIFIER),
      label=f"{ORDERED} {QUANTIFIER}",
    )
    if state.ordered_index or state.ordered_count < bounds.minimum:
      raise CommandGrammarError("ordered command arguments are incomplete")
    return
  if VALUES in node:
    bounds = parse_quantifier(
      node.get(QUANTIFIER),
      label=f"{VALUES} {QUANTIFIER}",
    )
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
      for value, description in slot_candidates(
        {token: entry},
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
  for token, entry in resolved_switches(node, context).items():
    bounds = switch_quantifier(entry)
    count = state.switch_counts.get(token, 0)
    if bounds.maximum is not None and count >= bounds.maximum:
      continue
    if token.startswith(prefix):
      result.append(Completion(token, switch_description(entry)))
  return result


def _pending_items(
  state: WalkState,
  context: Context,
  prefix: str,
  *,
  describe: bool,
) -> tuple[list[Completion], bool]:
  if state.pending_slot is None:
    return [], False
  result = [
    Completion(token, description, True)
    for token, description in slot_candidates(
      state.pending_slot,
      context,
      describe_generic=describe,
    ).items()
    if token.startswith(prefix)
  ]
  bounds = parse_quantifier(
    state.pending_slot.get(QUANTIFIER),
    label="parameter quantifier",
  )
  return result, state.pending_slot_count < bounds.minimum


def _node_items(
  state: WalkState,
  context: Context,
  prefix: str,
  *,
  include_terminal: bool,
  describe: bool,
) -> tuple[list[Completion], ResolvedCompletionSpec]:
  node = state.node
  entries, values, spec = resolved_node(node, context)
  result, pending_required = _pending_items(
    state,
    context,
    prefix,
    describe=describe,
  )
  if pending_required:
    return result, spec
  if ORDERED in node:
    bounds = parse_quantifier(
      node.get(QUANTIFIER),
      label=f"{ORDERED} {QUANTIFIER}",
    )
    if bounds.maximum is None or state.ordered_count < bounds.maximum:
      slot = node[ORDERED][state.ordered_index]
      result.extend(
        Completion(token, description, True)
        for token, description in slot_candidates(
          slot,
          context,
          describe_generic=describe,
        ).items()
        if token.startswith(prefix)
      )
    result.extend(_switch_items(node, state, context, prefix))
    return result, spec
  if include_terminal and TERMINAL in node and LAST_TERMINAL.startswith(prefix):
    result.append(Completion(LAST_TERMINAL, node[TERMINAL]))
  bounds = parse_quantifier(
    node.get(QUANTIFIER),
    label=f"{VALUES} {QUANTIFIER}",
  )
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
    result.extend(
      Completion(token, None, True)
      for token in values
      if token.startswith(prefix)
    )
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
