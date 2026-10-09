from __future__ import annotations

import json
import time
from pathlib import Path

from .lane_diagnostics import LaneDiagnostics
from .lane_metadata_cache import ensure_lane_metadata
from .lane_projection import ProjectionRule
from .lane_render import render_lanes
from .lane_selection import LaneSelectionStore
from .relationship_bootstrap import ensure_relationship_rules
from .runtime_identity import runtime_writer_identity


DIRECTION_SWITCHES = {
  "--dependencies": "dependencies",
  "--dependents": "dependents",
  "--single": "single",
}


def handle_lane_selection(
  root: Path,
  words: list[str],
  diagnostics: LaneDiagnostics | None = None,
) -> int:
  store = LaneSelectionStore(root)
  current = store.read()
  writer = runtime_writer_identity()
  if words == ["lanes", "clear"]:
    if current.revision is None:
      raise ValueError("lane selection is missing")
    store.clear(expected_revision=current.revision)
    print(json.dumps({"selection": None}, separators=(",", ":")))
    return 0

  if words[:2] != ["lanes", "select"]:
    raise ValueError("invalid lanes command")

  tail, mode, as_json, count_only, refresh = _selection_arguments(words[2:])
  if not tail:
    raise ValueError("lane selection requires at least one root")

  action = "select"
  if tail[0] in {"add", "remove", "exclude"}:
    action = tail.pop(0)
  if not tail:
    raise ValueError(f"lanes select {action} requires at least one issue")
  if any(not value.isdecimal() or int(value) <= 0 for value in tail):
    raise ValueError("lane selection issue IDs must be positive integers")
  if count_only and action != "select":
    raise ValueError("--count applies only to lanes select")

  rules = tuple(ProjectionRule(value, mode) for value in tail)

  if action == "select":
    includes = rules
    excludes = ()
  else:
    if current.value is None or current.revision is None:
      raise ValueError("lane selection is missing")
    if action == "add":
      includes = tuple((*current.value.includes, *rules))
      excludes = current.value.excludes
    elif action == "remove":
      remove_set = set(rules)
      includes = tuple(
        rule for rule in current.value.includes
        if rule not in remove_set
      )
      excludes = current.value.excludes
      if not includes:
        raise ValueError("remove would leave an empty selection; use clear")
    else:
      includes = current.value.includes
      excludes = tuple((*current.value.excludes, *rules))

  _prepare(
    root,
    includes,
    excludes,
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )

  started = time.perf_counter()
  if count_only:
    projected = store.project_rules(includes, excludes)
    if diagnostics is not None:
      diagnostics.phase("decomposition", started)
    print(len(projected.closure))
    return 0

  if action == "select":
    result = store.select_rules(
      rules,
      writer,
      expected_revision=current.revision,
    )
  elif action == "add":
    result = store.add_rules(
      rules,
      writer,
      expected_revision=current.revision,
    )
  elif action == "remove":
    result = store.remove_rules(
      rules,
      writer,
      expected_revision=current.revision,
    )
  else:
    result = store.exclude_rules(
      rules,
      writer,
      expected_revision=current.revision,
    )
  if diagnostics is not None:
    diagnostics.phase("decomposition", started)

  if as_json:
    print(json.dumps(result.value.to_json_value(), separators=(",", ":")))
  else:
    started = time.perf_counter()
    for line in render_lanes(
      root,
      titles=False,
      diagnostics=diagnostics,
    ):
      print(line)
    if diagnostics is not None:
      diagnostics.phase("render", started)
  return 0


def _prepare(
  root: Path,
  includes: tuple[ProjectionRule, ...],
  excludes: tuple[ProjectionRule, ...],
  writer,
  *,
  refresh: bool,
  diagnostics: LaneDiagnostics | None,
) -> None:
  started = time.perf_counter()
  relationships = ensure_relationship_rules(
    root,
    includes,
    excludes,
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )
  if diagnostics is not None:
    diagnostics.phase("relationships", started)

  started = time.perf_counter()
  ensure_lane_metadata(
    root,
    tuple(relationships.issues),
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )
  if diagnostics is not None:
    diagnostics.phase("metadata", started)


def _selection_arguments(
  words: list[str],
) -> tuple[list[str], str, bool, bool, bool]:
  positional: list[str] = []
  modes: list[str] = []
  as_json = False
  count_only = False
  refresh = False

  for token in words:
    if token in DIRECTION_SWITCHES:
      modes.append(DIRECTION_SWITCHES[token])
    elif token == "--json":
      as_json = True
    elif token == "--count":
      count_only = True
    elif token == "--refresh":
      refresh = True
    elif token.startswith("--"):
      raise ValueError(f"unsupported lanes select switch: {token}")
    else:
      positional.append(token)

  if len(modes) > 1:
    raise ValueError(
      "--dependencies, --dependents, and --single are mutually exclusive"
    )
  mode = "both" if not modes else modes[0]
  return positional, mode, as_json, count_only, refresh
