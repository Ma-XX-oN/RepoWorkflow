from __future__ import annotations

import json
import time
from pathlib import Path

from .lane_diagnostics import LaneDiagnostics
from .lane_metadata_cache import ensure_lane_metadata
from .lane_selection import LaneSelectionStore
from .lane_traversal import (
  FollowPolicy,
  ShowChildrenPolicy,
  parse_follow_arguments,
  parse_show_children_arguments,
)
from .lane_render import render_lanes
from .relationship_bootstrap import ensure_relationship_graph
from .runtime_identity import runtime_writer_identity


FOLLOW_GROUP_KINDS = frozenset({
  "group", "feature", "epic", "initiative"
})


def _follow_count_candidates(words: list[str]) -> tuple[int, ...]:
  return tuple(
    index
    for index, token in enumerate(words)
    if (
      token.isdecimal()
      and int(token) > 0
      and index >= 2
      and words[index - 2] == "--follow"
      and words[index - 1] in FOLLOW_GROUP_KINDS
    )
  )


def _consume_follow_count(words: list[str], index: int) -> bool:
  if index >= len(words):
    return False
  token = words[index]
  if not token.isdecimal() or int(token) <= 0:
    return False
  candidates = _follow_count_candidates(words)
  ordinary_values = tuple(
    position
    for position, value in enumerate(words)
    if value.isdecimal() and int(value) > 0 and position not in candidates
  )
  return bool(
    ordinary_values
    or not candidates
    or index != candidates[-1]
  )


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
  (
    tail,
    as_json,
    count_only,
    refresh,
    requested_follow,
    requested_show_children,
    legend,
  ) = _selection_arguments(words[2:])
  if legend and (as_json or count_only):
    raise ValueError('--legend requires graphical output')
  if not tail:
    raise ValueError("lane selection requires at least one root")

  if tail[0] == "add":
    if current.revision is None or current.value is None:
      raise ValueError("lane selection is missing")
    follow = current.value.follow if requested_follow is None else requested_follow
    show_children = (
      current.value.show_children
      if requested_show_children is None
      else requested_show_children
    )
    additions = tuple(tail[1:])
    desired = tuple(sorted(
      set(current.value.roots) | {str(int(value)) for value in additions},
      key=int,
    ))
    _prepare(
      root,
      desired,
      writer,
      refresh=refresh,
      diagnostics=diagnostics,
      follow=follow,
      show_children=show_children,
    )
    started = time.perf_counter()
    result = store.add(
      additions,
      writer,
      expected_revision=current.revision,
      follow=follow,
      show_children=show_children,
    )
    if diagnostics is not None:
      diagnostics.phase("decomposition", started)
  elif tail[0] == "remove":
    if current.revision is None or current.value is None:
      raise ValueError("lane selection is missing")
    follow = current.value.follow if requested_follow is None else requested_follow
    show_children = (
      current.value.show_children
      if requested_show_children is None
      else requested_show_children
    )
    removals = tuple(tail[1:])
    removed = {str(int(value)) for value in removals}
    desired = tuple(
      value for value in current.value.roots
      if value not in removed
    )
    if desired:
      _prepare(
        root,
        desired,
        writer,
        refresh=refresh,
        diagnostics=diagnostics,
        follow=follow,
        show_children=show_children,
      )
    started = time.perf_counter()
    result = store.remove(
      removals,
      writer,
      expected_revision=current.revision,
      follow=follow,
      show_children=show_children,
    )
    if diagnostics is not None:
      diagnostics.phase("decomposition", started)
  else:
    follow = FollowPolicy() if requested_follow is None else requested_follow
    show_children = (
      ShowChildrenPolicy()
      if requested_show_children is None
      else requested_show_children
    )
    desired = tuple(tail)
    _prepare(
      root,
      desired,
      writer,
      refresh=refresh,
      diagnostics=diagnostics,
      follow=follow,
      show_children=show_children,
    )
    started = time.perf_counter()
    if count_only:
      projected = store.project(
        desired,
        follow=follow,
        show_children=show_children,
      )
      if diagnostics is not None:
        diagnostics.phase("decomposition", started)
      print(len(projected.closure))
      return 0
    result = store.select(
      desired,
      writer,
      expected_revision=current.revision,
      follow=follow,
      show_children=show_children,
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
    if legend:
      print()
      print("Legend: ○ not_started  ● active  ◎ in_review  ✓ accepted  ♥ completed  ✕ aborted")
    if diagnostics is not None:
      diagnostics.phase("render", started)
  return 0


def _prepare(
  root: Path,
  roots: tuple[str | int, ...],
  writer,
  *,
  refresh: bool,
  diagnostics: LaneDiagnostics | None,
  follow: FollowPolicy,
  show_children: ShowChildrenPolicy,
) -> None:
  started = time.perf_counter()
  relationships = ensure_relationship_graph(
    root,
    roots,
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
    follow=follow,
    show_children=show_children,
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
) -> tuple[
  list[str],
  bool,
  bool,
  bool,
  FollowPolicy | None,
  ShowChildrenPolicy | None,
  bool,
]:
  positional: list[str] = []
  follow_values: list[tuple[str, str | None]] = []
  show_children_values: list[str] = []
  as_json = False
  count_only = False
  refresh = False
  legend = False
  index = 0
  while index < len(words):
    token = words[index]
    if token == "--json":
      as_json = True
      index += 1
      continue
    if token == "--count":
      count_only = True
      index += 1
      continue
    if token == "--refresh":
      refresh = True
      index += 1
      continue
    if token == "--legend":
      legend = True
      index += 1
      continue
    if token == "--follow":
      if index + 1 >= len(words):
        raise ValueError("--follow requires a group kind")
      kind = words[index + 1]
      count = None
      index += 2
      if _consume_follow_count(words, index):
        count = words[index]
        index += 1
      follow_values.append((kind, count))
      continue
    if token == "--show-children":
      if index + 1 >= len(words):
        raise ValueError("--show-children requires a group kind")
      show_children_values.append(words[index + 1])
      index += 2
      continue
    positional.append(token)
    index += 1
  follow = None if not follow_values else parse_follow_arguments(follow_values)
  show_children = (
    None
    if not show_children_values
    else parse_show_children_arguments(show_children_values)
  )
  return positional, as_json, count_only, refresh, follow, show_children, legend
