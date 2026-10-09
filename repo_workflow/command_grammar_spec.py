from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeAlias

from .command_grammar_support import (
  CommandGrammarError,
  ORDERED,
  QUANTIFIER,
  SWITCHES,
  is_parameter,
  parse_quantifier,
  validate_description,
  validate_ordered,
  validate_switches,
)

LAST_TERMINAL = "<last-terminal>"
TERMINAL = ""
VALUES = "_values"
VALUE_DESCRIPTION = "_value_description"
NODE_DESCRIPTION = "_description"
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
        description = (
          entry if isinstance(entry, str)
          else entry.get(NODE_DESCRIPTION, entry.get(TERMINAL))
        )
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
      raise CommandGrammarError(
        f"{label} cannot combine {ORDERED!r} and {VALUES!r}"
      )
  if QUANTIFIER in node and ORDERED not in node and VALUES not in node:
    bounds = parse_quantifier(node[QUANTIFIER], label=f"{label}[{QUANTIFIER!r}]")
    repeated = bounds.minimum != 1 or bounds.maximum != 1
    if repeated:
      nested = [
        token
        for token, entry in node.items()
        if not token.startswith("_")
        and token != TERMINAL
        and isinstance(entry, dict)
      ]
      if nested:
        raise CommandGrammarError(
          f"{label} repeated command alternatives must be terminal; "
          f"use {ORDERED!r} for repeated multi-token structure"
        )
  for token, entry in node.items():
    if not isinstance(token, str):
      raise CommandGrammarError(f"{label} keys must be strings")
    if token == TERMINAL:
      validate_description(entry, f"{label}[{TERMINAL!r}]")
      continue
    if token == VALUES:
      _validate_value_source(entry, f"{label}[{VALUES!r}]")
      continue
    if token in {VALUE_DESCRIPTION, NODE_DESCRIPTION}:
      validate_description(entry, f"{label}[{token!r}]")
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


def resolved_switches(node: dict, context: Context) -> dict:
  source = node.get(SWITCHES, {})
  value = source(context) if callable(source) else source
  if not isinstance(value, dict):
    raise CommandGrammarError(f"{SWITCHES} provider must return a dictionary")
  validate_switches(value, SWITCHES)
  return value


def resolved_node(
  node: dict,
  context: Context,
) -> tuple[dict[str, CommandEntry], frozenset[str], ResolvedCompletionSpec]:
  specials = {
    TERMINAL, VALUES, VALUE_DESCRIPTION, NODE_DESCRIPTION,
    QUANTIFIER, SWITCHES, ORDERED,
  }
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
  entries, values, _ = resolved_node(node, context)
  return entries, set(values)
