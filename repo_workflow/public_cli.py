from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from .command_diagnostics import analyse_failure, render_failure
from .command_grammar import (
  CommandGrammarError,
  Context,
  completion_items,
  completion_response,
  parse_tokens,
)
from .config import load_config
from .dependency_sync_cli import dependency_sync_command
from .high_risk import associate_high_risk
from .issue_info_cli import show_issue_info
from .invocation_identity import ensure_public_runtime_identity
from .issue_list import list_issues
from .lane_diagnostics import LaneDiagnostics
from .lane_inspection import (
  refresh_current_lane_metadata,
  refresh_current_lane_selection,
)
from .lane_list import render_lane_list
from .lane_selection import LaneSelectionStore
from .lane_selection_cli import handle_lane_selection
from .lane_render import render_lanes, set_color_setting
from .relationship_store import RelationshipStore
from .runtime_identity import runtime_writer_identity
from .ticket_merge import configure_ticket_merge_driver
from .issue_start import start_issue
from .public_commands import COMMANDS, PUBLIC_COMMANDS
from .version_adapter import read_version, run_transition
from .workflow_state import derive_plan, discover_facts, render_human, state_name
from .workflow_transitions import validate_integration, validate_regression
from .workspace_cli import handle_workspace


def _contexts(root: Path):
  general = Context(root, legal_only=False)
  if not (root / ".ci" / "repoworkflow.json").exists():
    return general, general, None, None, None

  facts = discover_facts(root)
  plan = derive_plan(facts)
  state = state_name(facts)
  return (
    general,
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
    legal_transitions=() if plan is None else plan.transitions,
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


def _requires_public_runtime_identity(words: list[str]) -> bool:
  command = words[0]
  if command == "lanes":
    if words[1] in {"list", "view"}:
      return "--refresh" in words
    return True
  if command == "settings":
    return True
  if command == "issue":
    if words[1] == "start":
      return True
    if words[1].isdecimal() and "dependency" in words:
      return "--compare" not in words
    return False
  if command == "workspace":
    return words[1] in {"create", "claim", "release", "resume", "close"}
  if command == "high-risk":
    return True
  return False


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

  configure_ticket_merge_driver(root, engine_root)

  if _requires_public_runtime_identity(words):
    ensure_public_runtime_identity(root)

  command = words[0]
  if command == "init":
    print(
      "RepoWorkflow error: rwf init execution is not implemented yet.",
      file=sys.stderr,
    )
    return 2

  if command == "workspace":
    return handle_workspace(root, words)

  if command == "lanes":
    diagnostics = LaneDiagnostics(root, tuple(words))
    try:
      result = _handle_lanes(root, words, diagnostics)
    except Exception as error:
      diagnostics.finish(error=error)
      raise
    diagnostics.finish()
    return result

  if command == "settings":
    print(set_color_setting(root, words[2], runtime_writer_identity()))
    return 0

  if command == "issue":
    if words[1].isdecimal():
      return dependency_sync_command(root, tuple(words[1:]))
    if words[1] == "info":
      argument = words[2] if len(words) == 3 else None
      for line in show_issue_info(root, argument):
        print(line)
      return 0
    if words[1] == "list":
      for line in list_issues(root, words[2:]):
        print(line)
      return 0
    result = start_issue(root, words[2])
    print(json.dumps(result.to_json_value(), separators=(",", ":")))
    return 0

  if command == "high-risk":
    result = associate_high_risk(
      root,
      words[1:],
      runtime_writer_identity(),
    )
    print(json.dumps({
      "issue": result.lifecycle.issue,
      "high_risk_aliases": list(result.lifecycle.high_risk_aliases),
    }, separators=(",", ":")))
    return 0

  if command == "what-next":
    if plan is None or state is None:
      facts = discover_facts(root)
      plan = derive_plan(facts)
      state = state_name(facts)
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


def _handle_lanes(
  root: Path,
  words: list[str],
  diagnostics: LaneDiagnostics,
) -> int:
  if words[1] in {"list", "view"}:
    tail = words[2:]
    refresh = "--refresh" in tail
    links = "--links" in tail
    debug = "--debug" in tail
    ignored = {"--refresh", "--links", "--debug"}
    lane = next((x for x in tail if x not in ignored), None)
    if refresh:
      if words[1] == "list":
        refresh_current_lane_metadata(
          root,
          runtime_writer_identity(),
          diagnostics=diagnostics,
        )
      else:
        refresh_current_lane_selection(
          root,
          runtime_writer_identity(),
          diagnostics=diagnostics,
        )
    else:
      selection = LaneSelectionStore(root).read().value
      if selection is not None:
        diagnostics.hit("metadata", len(selection.closure))
        if words[1] == "view":
          diagnostics.hit("relationships", len(selection.closure))

    started = time.perf_counter()
    if words[1] == "list":
      if debug:
        raise ValueError("lanes list does not accept --debug")
      for line in render_lane_list(root, lane=lane, links=links):
        print(line)
      diagnostics.phase("render", started)
    else:
      if links:
        raise ValueError("lanes view does not accept --links")
      for line in render_lanes(
        root,
        lane=lane,
        titles=False,
        diagnostics=diagnostics,
      ):
        print(line)
      diagnostics.phase("render", started)
      _record_semantic_edges(root, diagnostics)
      if debug:
        print()
        for line in diagnostics.debug_lines():
          print(line)
    return 0

  result = handle_lane_selection(root, words, diagnostics=diagnostics)
  _record_semantic_edges(root, diagnostics)
  return result


def _record_semantic_edges(
  root: Path,
  diagnostics: LaneDiagnostics,
) -> None:
  selection = LaneSelectionStore(root).read().value
  if selection is None:
    return
  graph = RelationshipStore(root).read().graph
  visible = set(selection.closure)
  edges = [
    (int(source), int(target))
    for target in selection.closure
    for source in graph.issue(target).depends_on
    if source in visible
  ]
  diagnostics.set_semantic_edges(edges)


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


def _print_completion_items(items, *, describe: bool) -> None:
  if describe:
    width = max(len(item.token) for item in items)
    for item in items:
      if item.description is None:
        print(item.token)
      else:
        print(f"{item.token:<{width}}  {item.description}")
    return
  for item in items:
    print(item.token)


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

  response = completion_response(
    COMMANDS,
    legal,
    words,
    include_terminal=True,
    describe=describe,
  )
  if response.error is not None:
    print(response.error, file=sys.stderr)
    return 2

  items = list(response.items)
  if items:
    _print_completion_items(items, describe=describe)
    return 0

  if _completed_command_is_terminal(legal, words):
    return 0

  if failure is not None:
    return _print_failure(failure)
  return 0


def handle_help(root: Path, words: list[str]) -> int:
  help_words = [*words, ""]
  return handle_completion(root, help_words, describe=True)


def is_public_command(word: str) -> bool:
  return word in PUBLIC_COMMANDS
