from __future__ import annotations

from pathlib import Path
import time

from .lane_diagnostics import LaneDiagnostics
from .lane_metadata_cache import ensure_lane_metadata
from .lane_selection import LaneSelectionSnapshot, LaneSelectionStore
from .relationship_bootstrap import ensure_relationship_graph
from .state_store import WriterIdentity


def refresh_current_lane_metadata(
  root: Path,
  writer: WriterIdentity,
  diagnostics: LaneDiagnostics | None = None,
) -> LaneSelectionSnapshot:
  """Refresh display metadata only; never reread or mutate relationships."""
  current = LaneSelectionStore(root).read()
  if current.value is None:
    raise ValueError("lane selection is missing")

  started = time.perf_counter()
  ensure_lane_metadata(
    root,
    tuple(current.value.closure),
    writer,
    refresh=True,
    diagnostics=diagnostics,
  )
  if diagnostics is not None:
    diagnostics.phase("metadata", started)
  return current


def refresh_current_lane_selection(
  root: Path,
  writer: WriterIdentity,
  diagnostics: LaneDiagnostics | None = None,
) -> LaneSelectionSnapshot:
  store = LaneSelectionStore(root)
  current = store.read()
  if current.value is None or current.revision is None:
    raise ValueError("lane selection is missing")

  started = time.perf_counter()
  relationships = ensure_relationship_graph(
    root,
    current.value.roots,
    writer,
    refresh=True,
    diagnostics=diagnostics,
    follow=current.value.follow,
  )
  if diagnostics is not None:
    diagnostics.phase("relationships", started)

  started = time.perf_counter()
  ensure_lane_metadata(
    root,
    tuple(relationships.issues),
    writer,
    refresh=True,
    diagnostics=diagnostics,
  )
  if diagnostics is not None:
    diagnostics.phase("metadata", started)

  started = time.perf_counter()
  result = store.select(
    current.value.roots,
    writer,
    expected_revision=current.revision,
    follow=current.value.follow,
  )
  if diagnostics is not None:
    diagnostics.phase("decomposition", started)
  return result
