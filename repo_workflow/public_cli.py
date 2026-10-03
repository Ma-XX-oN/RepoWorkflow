from __future__ import annotations

import json
from pathlib import Path
import sys

from .command_diagnostics import analyse_failure, render_failure
from .command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  parse_tokens,
)
from .config import load_config
from .public_commands import COMMANDS, PUBLIC_COMMANDS
from .version_adapter import read_version, run_transition
from .workflow_state import derive_plan, discover_facts, render_human, state_name
from .workflow_transitions import validate_integration, validate_regression


def _contexts(root: Path):
  facts = discover_facts(root)
  plan = derive_plan(facts)
  state = state_name(facts)
  return (
    Context(root, legal_only=False),
    Context(root, legal_only=True),
    facts,
    plan,
    state,
  )


def _diagnose(
  root: Path,
  words: list[str],
  *,
  completion: bool,
):
  general, legal, facts, plan, state = _contexts(root)
  failure = analyse_failure(
    COMMANDS,
    words,
    general,
    legal,
    completion=completion,
    state_name=state,
    legal_transitions=plan.transitions,
  )
  return general, legal, facts, plan, state, failure


def _print_failure(failure) -> int:
  print(render_failure(failure), file=sys.stderr)
  return 2


def _version_transition(words: list[str]) -> tuple[str, ...] | None:
  if not words:
    return None
  if len(words) == 3 and words[:2] == ["task", "issue"]:
    int(words[2])
    return "task", "--issue", words[2]
  if (
    len(words) == 3
    and words[:2] == ["integrate", "increment"]
    and words[2] in {"patch", "minor"}
  ):
    return "integrate", "--increment", words[2]
  if words == ["release-major"]:
    return ("release-major",)
  raise CommandGrammarError("invalid version transition")


def handle_public(root: Path, words: list[str], *, engine_root: Path) -> int:
  general, legal, facts, plan, state, failure = _diagnose(
    root,
    words,
    completion=False,
  )
  if failure is not None:
    return _print_failure(failure)

  parse_tokens(COMMANDS, general, words)
  parse_tokens(COMMANDS, legal, words)

  command = words[0]
  if command == "what-next":
    if words == ["what-next", "--json"]:
      print(json.dumps(plan.to_json_value(), separators=(",", ":")))
    else:
      print(render_human(plan, state))
    return 0

  if command == "validate":
    if words == ["validate", "regression"]:
      outcome = validate_regression(root, engine_root=engine_root)
      return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]
    candidate = validate_integration(root, words[2])
    print(candidate)
    return 0

  if command == "version":
    config = load_config(root)
    version_words = words[1:]
    as_json = version_words == ["--json"]
    if as_json:
      transition = None
    else:
      transition = _version_transition(version_words)
    if transition is not None:
      run_transition(root, config, *transition)
    value = read_version(root, config)
    if as_json:
      print(json.dumps({"version": value}, separators=(",", ":")))
    else:
      print(value)
    return 0

  raise AssertionError("unreachable public command")


def _completed_command_is_terminal(
  legal: Context,
  words: list[str],
) -> bool:
  if not words or words[-1] != "":
    return False
  completed = words[:-1]
  if not completed:
    return False
  try:
    parse_tokens(COMMANDS, legal, completed)
  except CommandGrammarError:
    return False
  return True


def handle_completion(
  root: Path,
  words: list[str],
  *,
  describe: bool,
) -> int:
  general, legal, facts, plan, state, failure = _diagnose(
    root,
    words,
    completion=True,
  )

  items = completion_items(
    COMMANDS,
    legal,
    words,
    include_terminal=True,
  )
  if items:
    if describe:
      width = max(len(item.token) for item in items)
      for item in items:
        if item.description is None:
          print(item.token)
        else:
          print(f"{item.token:<{width}}  {item.description}")
    else:
      for item in items:
        print(item.token)
    return 0

  if _completed_command_is_terminal(legal, words):
    return 0

  if failure is not None:
    return _print_failure(failure)
  return 0


def is_public_command(word: str) -> bool:
  return word in PUBLIC_COMMANDS
