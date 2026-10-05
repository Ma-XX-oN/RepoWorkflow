from __future__ import annotations

from pathlib import Path

from .lane_metadata_cache import ensure_lane_metadata
from .lane_selection import LaneSelectionSnapshot, LaneSelectionStore
from .relationship_bootstrap import ensure_relationship_graph
from .state_store import WriterIdentity


def refresh_current_lane_selection(
  root: Path,
  writer: WriterIdentity,
) -> LaneSelectionSnapshot:
  store = LaneSelectionStore(root)
  current = store.read()
  if current.value is None or current.revision is None:
    raise ValueError("lane selection is missing")

  relationships = ensure_relationship_graph(
    root,
    current.value.roots,
    writer,
    refresh=True,
  )
  ensure_lane_metadata(
    root,
    tuple(relationships.issues),
    writer,
    refresh=True,
  )
  return store.select(
    current.value.roots,
    writer,
    expected_revision=current.revision,
  )
