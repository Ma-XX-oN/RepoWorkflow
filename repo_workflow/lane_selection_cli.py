from __future__ import annotations

import json
from pathlib import Path

from .lane_selection import LaneSelectionStore
from .lane_render import render_lanes
from .relationship_bootstrap import ensure_relationship_graph
from .runtime_identity import runtime_writer_identity


def handle_lane_selection(root: Path, words: list[str]) -> int:
  store = LaneSelectionStore(root)
  current = store.read()
  writer = runtime_writer_identity()
  if words == ["lanes", "clear"]:
    if current.revision is None:
      raise ValueError("lane selection is missing")
    result = store.clear(expected_revision=current.revision)
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
    if current.revision is None:
      raise ValueError("lane selection is missing")
    ensure_relationship_graph(
      root,
      tuple(tail[1:]),
      writer,
      refresh=refresh,
    )
    result = store.add(
      tuple(tail[1:]), writer, expected_revision=current.revision
    )
  elif tail[0] == "remove":
    if current.revision is None or current.value is None:
      raise ValueError("lane selection is missing")
    removed = {str(int(value)) for value in tail[1:]}
    remaining = tuple(
      value for value in current.value.roots
      if value not in removed
    )
    if refresh and remaining:
      ensure_relationship_graph(
        root,
        remaining,
        writer,
        refresh=True,
      )
    result = store.remove(
      tuple(tail[1:]), writer, expected_revision=current.revision
    )
  else:
    ensure_relationship_graph(
      root,
      tuple(tail),
      writer,
      refresh=refresh,
    )
    result = store.select(
      tuple(tail), writer, expected_revision=current.revision
    )
  if as_json:
    print(json.dumps(result.value.to_json_value(), separators=(",", ":")))
  else:
    for line in render_lanes(root, titles=False):
      print(line)
  return 0
