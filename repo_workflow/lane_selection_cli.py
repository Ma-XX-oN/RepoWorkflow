from __future__ import annotations

import json
from pathlib import Path

from .lane_diagnostics import LaneDiagnostics
from .lane_metadata_cache import ensure_lane_metadata
from .lane_selection import LaneSelectionStore
from .lane_render import render_lanes
from .relationship_bootstrap import ensure_relationship_graph
from .runtime_identity import runtime_writer_identity


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
  tail = words[2:]
  as_json = "--json" in tail
  refresh = "--refresh" in tail
  tail = [
    word for word in tail
    if word not in {"--json", "--refresh"}
  ]
  if not tail:
    raise ValueError("lane selection requires at least one root")

  if tail[0] == "add":
    if current.revision is None or current.value is None:
      raise ValueError("lane selection is missing")
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
    )
    result = store.add(
      additions,
      writer,
      expected_revision=current.revision,
    )
  elif tail[0] == "remove":
    if current.revision is None or current.value is None:
      raise ValueError("lane selection is missing")
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
      )
    result = store.remove(
      removals,
      writer,
      expected_revision=current.revision,
    )
  else:
    desired = tuple(tail)
    _prepare(
      root,
      desired,
      writer,
      refresh=refresh,
      diagnostics=diagnostics,
    )
    result = store.select(
      desired,
      writer,
      expected_revision=current.revision,
    )

  if as_json:
    print(json.dumps(result.value.to_json_value(), separators=(",", ":")))
  else:
    for line in render_lanes(root, titles=False):
      print(line)
  return 0


def _prepare(
  root: Path,
  roots: tuple[str | int, ...],
  writer,
  *,
  refresh: bool,
  diagnostics: LaneDiagnostics | None,
) -> None:
  relationships = ensure_relationship_graph(
    root,
    roots,
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )
  ensure_lane_metadata(
    root,
    tuple(relationships.issues),
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )
