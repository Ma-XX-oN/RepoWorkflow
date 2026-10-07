from __future__ import annotations

from collections.abc import Callable

from .graph_quality import long_route_row_score
from .graph_render_types import GraphLayoutError, Placement, SemanticEdge


def choose_long_route_row(
  edge: SemanticEdge,
  placements: dict[str, Placement],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
  crossing_cost: Callable[[int], int],
  candidate_valid: Callable[[int], bool] | None = None,
) -> int:
  source = placements[edge.source]
  target = placements[edge.target]
  occupied = {
    placement.row
    for placement in placements.values()
    if source.column < placement.column < target.column
  }

  fallback_stop = max_node_row + len(used_rows) + 3
  candidates = {
    source.row,
    target.row,
    *range(max_node_row + 1),
    *range(max_node_row + 1, fallback_stop),
  }
  available = [
    row
    for row in candidates
    if (
      row not in occupied
      and _long_row_is_compatible(
        edge,
        used_rows.get(row, []),
      )
    )
  ]
  if not available:
    raise GraphLayoutError(
      f"no bounded long-route row candidate is available for "
      f"{edge.source!r} -> {edge.target!r}"
    )

  ordered = sorted(
    available,
    key=lambda row: (
      crossing_cost(row),
      long_route_row_score(
        source.row,
        target.row,
        row,
      ),
    ),
  )
  for row in ordered:
    if candidate_valid is None or candidate_valid(row):
      return row
  raise GraphLayoutError(
    "no semantically valid bounded long-route row candidate is available "
    f"for {edge.source!r} -> {edge.target!r}"
  )


def _long_row_is_compatible(
  edge: SemanticEdge,
  existing: list[SemanticEdge],
) -> bool:
  if not existing:
    return True
  edges = [*existing, edge]
  return (
    len({item.source for item in edges}) == 1
    or len({item.target for item in edges}) == 1
  )
