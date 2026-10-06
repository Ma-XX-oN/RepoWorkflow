from __future__ import annotations

from .graph_quality import long_route_row_score
from .graph_render_types import Placement, SemanticEdge


def choose_long_route_row(
  edge: SemanticEdge,
  placements: dict[str, Placement],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
) -> int:
  source = placements[edge.source]
  target = placements[edge.target]
  occupied = {
    placement.row
    for placement in placements.values()
    if source.column < placement.column < target.column
  }
  candidates = {
    source.row,
    target.row,
    *range(max_node_row + 1),
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
    row = max_node_row + 1
    while not _long_row_is_compatible(
      edge,
      used_rows.get(row, []),
    ):
      row += 1
    return row

  return min(
    available,
    key=lambda row: long_route_row_score(
      source.row,
      target.row,
      row,
    ),
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
