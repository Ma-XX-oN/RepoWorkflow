from __future__ import annotations

from dataclasses import dataclass

from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  LayoutPlan,
)


@dataclass(frozen=True, order=True)
class RouteQuality:
  max_vertical_span: int
  total_vertical_cells: int
  bend_count: int
  opposing_adjacent_verticals: int
  crossing_count: int
  vertical_track_count: int
  width: int


def measure_layout(layout: LayoutPlan) -> RouteQuality:
  edge_bits: dict[
    tuple[str, str],
    dict[tuple[int, int], int],
  ] = {}
  vertical_tracks: set[int] = set()
  directions: dict[tuple[int, int], set[int]] = {}

  for point, contributions in layout.cells.items():
    for contribution in contributions:
      key = contribution.edge.key
      edge_bits.setdefault(key, {})
      edge_bits[key][point] = (
        edge_bits[key].get(point, 0)
        | contribution.bits
      )
      if contribution.bits & (_U | _D):
        vertical_tracks.add(point[0])
      if contribution.vertical_direction:
        directions.setdefault(point, set()).add(
          contribution.vertical_direction
        )

  max_vertical_span = 0
  total_vertical_cells = 0
  bend_count = 0
  for points in edge_bits.values():
    vertical_rows = [
      point[1]
      for point, bits in points.items()
      if bits & (_U | _D)
    ]
    if vertical_rows:
      max_vertical_span = max(
        max_vertical_span,
        max(vertical_rows) - min(vertical_rows),
      )
      total_vertical_cells += len(vertical_rows)
    bend_count += sum(
      1
      for bits in points.values()
      if bits & (_L | _R) and bits & (_U | _D)
    )

  opposing = 0
  for (x, y), values in directions.items():
    right = directions.get((x + 1, y), set())
    if (
      (1 in values and -1 in right)
      or (-1 in values and 1 in right)
    ):
      opposing += 1

  crossing_count = 0
  for contributions in layout.cells.values():
    per_edge: dict[tuple[str, str], int] = {}
    for contribution in contributions:
      key = contribution.edge.key
      per_edge[key] = per_edge.get(key, 0) | contribution.bits
    if len(per_edge) < 2:
      continue
    has_horizontal = any(
      bits & (_L | _R)
      for bits in per_edge.values()
    )
    has_vertical = any(
      bits & (_U | _D)
      for bits in per_edge.values()
    )
    if has_horizontal and has_vertical:
      crossing_count += 1

  return RouteQuality(
    max_vertical_span=max_vertical_span,
    total_vertical_cells=total_vertical_cells,
    bend_count=bend_count,
    opposing_adjacent_verticals=opposing,
    crossing_count=crossing_count,
    vertical_track_count=len(vertical_tracks),
    width=layout.width,
  )


def long_route_row_score(
  source_row: int,
  target_row: int,
  route_row: int,
) -> tuple[int, int, int, int, int]:
  low = min(source_row, target_row)
  high = max(source_row, target_row)
  excursion = max(low - route_row, route_row - high, 0)
  vertical = (
    abs(source_row - route_row)
    + abs(target_row - route_row)
  )
  bends = int(route_row != source_row) + int(
    route_row != target_row
  )
  return (
    excursion,
    vertical,
    bends,
    abs(route_row - source_row),
    route_row,
  )
