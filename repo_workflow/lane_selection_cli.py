from __future__ import annotations

import json
from pathlib import Path

from .lane_selection import LaneSelectionStore
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
  if tail[0] == "add":
    if current.revision is None:
      raise ValueError("lane selection is missing")
    result = store.add(
      tuple(tail[1:]), writer, expected_revision=current.revision
    )
  elif tail[0] == "remove":
    if current.revision is None:
      raise ValueError("lane selection is missing")
    result = store.remove(
      tuple(tail[1:]), writer, expected_revision=current.revision
    )
  else:
    result = store.select(
      tuple(tail), writer, expected_revision=current.revision
    )
  print(json.dumps(result.value.to_json_value(), separators=(",", ":")))
  return 0
