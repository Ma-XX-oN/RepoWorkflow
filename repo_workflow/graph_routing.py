from __future__ import annotations

from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Column,
  Contribution,
  Placement,
  SemanticEdge,
)


def edge_item_key(edge: SemanticEdge) -> tuple:
  return "edge", edge.source, edge.target


def dogleg_source_key(edge: SemanticEdge) -> tuple:
  return "dogleg-source", edge.source, edge.target


def dogleg_target_key(edge: SemanticEdge) -> tuple:
  return "dogleg-target", edge.source, edge.target


def route_adjacent(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  track_x: int,
  *,
  bundle: tuple[int, int] | None = None,
) -> None:
  source = placements[edge.source]
  target = placements[edge.target]
  source_x = starts[source.column] + columns[source.column].width
  target_x = starts[target.column] - 1
  _horizontal(cells, edge, source_x, track_x, source.row, bundle)
  _vertical(cells, edge, track_x, source.row, target.row, bundle)
  _horizontal(cells, edge, track_x, target_x, target.row, bundle)


def route_adjacent_dogleg(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  source_track_x: int,
  target_track_x: int,
  track_y: int,
) -> None:
  source = placements[edge.source]
  target = placements[edge.target]
  source_x = starts[source.column] + columns[source.column].width
  target_x = starts[target.column] - 1
  _horizontal(cells, edge, source_x, source_track_x, source.row, None)
  _vertical(cells, edge, source_track_x, source.row, track_y, None)
  _horizontal(cells, edge, source_track_x, target_track_x, track_y, None)
  _vertical(cells, edge, target_track_x, track_y, target.row, None)
  _horizontal(cells, edge, target_track_x, target_x, target.row, None)


def route_long(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  track_y: int,
) -> None:
  source = placements[edge.source]
  target = placements[edge.target]
  item = edge_item_key(edge)
  source_track = tracks[(source.column, item)]
  target_track = tracks[(target.column - 1, item)]
  source_x = starts[source.column] + columns[source.column].width
  target_x = starts[target.column] - 1
  _horizontal(cells, edge, source_x, source_track, source.row, None)
  _vertical(cells, edge, source_track, source.row, track_y, None)
  _horizontal(cells, edge, source_track, target_track, track_y, None)
  _vertical(cells, edge, target_track, track_y, target.row, None)
  _horizontal(cells, edge, target_track, target_x, target.row, None)


def _add(
  cells: dict[tuple[int, int], list[Contribution]],
  point: tuple[int, int],
  edge: SemanticEdge,
  bits: int,
  bundle: tuple[int, int] | None,
  vertical_direction: int = 0,
) -> None:
  cells.setdefault(point, []).append(
    Contribution(edge, bits, bundle, vertical_direction)
  )


def _horizontal(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
  x1: int,
  x2: int,
  y: int,
  bundle: tuple[int, int] | None,
) -> None:
  if x2 < x1:
    x1, x2 = x2, x1
  for x in range(x1, x2 + 1):
    bits = 0
    if x > x1:
      bits |= _L
    if x < x2:
      bits |= _R
    if bits:
      _add(cells, (x, y), edge, bits, bundle)


def _vertical(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
  x: int,
  y1: int,
  y2: int,
  bundle: tuple[int, int] | None,
) -> None:
  direction = 0
  if y2 > y1:
    direction = 1
  elif y2 < y1:
    direction = -1
  low, high = sorted((y1, y2))
  for y in range(low, high + 1):
    bits = 0
    if y > low:
      bits |= _U
    if y < high:
      bits |= _D
    if bits:
      _add(
        cells,
        (x, y),
        edge,
        bits,
        bundle,
        direction,
      )
