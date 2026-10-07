from __future__ import annotations

from collections.abc import Callable

from .graph_quality import long_route_row_score
from .graph_render_types import GraphLayoutError, Placement, SemanticEdge


def long_route_candidates(
  edge: SemanticEdge,
  placements: dict[str, Placement],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
  crossing_cost: Callable[[int], int],
  *,
  fallback_rows: int = 3,
) -> tuple[int, ...]:
  source = placements[edge.source]
  target = placements[edge.target]
  occupied = {
    placement.row
    for placement in placements.values()
    if source.column < placement.column < target.column
  }

  fallback_stop = max_node_row + max(fallback_rows, 1) + 1
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
        placements,
      )
    )
  ]
  if not available:
    return ()

  return tuple(sorted(
    available,
    key=lambda row: (
      crossing_cost(row),
      long_route_row_score(
        source.row,
        target.row,
        row,
      ),
    ),
  ))


def choose_long_route_row(
  edge: SemanticEdge,
  placements: dict[str, Placement],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
  crossing_cost: Callable[[int], int],
  candidate_valid: Callable[[int], bool] | None = None,
) -> int:
  for row in long_route_candidates(
    edge,
    placements,
    max_node_row,
    used_rows,
    crossing_cost,
    fallback_rows=len(used_rows) + 3,
  ):
    if candidate_valid is None or candidate_valid(row):
      return row
  raise GraphLayoutError(
    "no semantically valid bounded long-route row candidate is available "
    f"for {edge.source!r} -> {edge.target!r}"
  )


def _long_row_is_compatible(
  edge: SemanticEdge,
  existing: list[SemanticEdge],
  placements: dict[str, Placement],
) -> bool:
  if not existing:
    return True

  component = [edge]
  pending = [edge]
  remaining = list(existing)
  while pending:
    current = pending.pop()
    current_span = _edge_span(current, placements)
    connected = [
      item
      for item in remaining
      if _spans_overlap(
        current_span,
        _edge_span(item, placements),
      )
    ]
    if not connected:
      continue
    for item in connected:
      remaining.remove(item)
      component.append(item)
      pending.append(item)

  if len(component) == 1:
    return True
  return (
    len({item.source for item in component}) == 1
    or len({item.target for item in component}) == 1
  )


def _edge_span(
  edge: SemanticEdge,
  placements: dict[str, Placement],
) -> tuple[int, int]:
  source = placements[edge.source].column
  target = placements[edge.target].column
  return source, target - 1


def _spans_overlap(
  left: tuple[int, int],
  right: tuple[int, int],
) -> bool:
  return max(left[0], right[0]) <= min(left[1], right[1])
