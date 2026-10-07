from __future__ import annotations

from .graph_render_model import ValidatedGraph
from .graph_route_semantics import (
  long_route_candidate_valid,
  route_candidate_preserves_reachability,
  validate_long_route_candidate,
  validate_rendered_reachability,
  validate_route_candidate_reachability,
)
from .graph_render_types import (
  Column,
  Contribution,
  GraphLayoutError,
  Placement,
  RouteRecord,
)


def validate_routes(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  routes: tuple[RouteRecord, ...],
) -> None:
  expected = {
    (source, target)
    for source, targets in validated.adjacency.items()
    for target in targets
  }

  route_edges = {(route.source, route.target) for route in routes}
  if route_edges != expected or len(routes) != len(expected):
    raise GraphLayoutError(
      "logical routes do not match semantic relationships"
    )

  routed_cells: dict[tuple[str, str], set[tuple[int, int]]] = {}
  for point, contributions in cells.items():
    for contribution in contributions:
      key = contribution.edge.key
      if key not in expected:
        raise GraphLayoutError(
          "routed geometry contains an unknown semantic edge"
        )
      routed_cells.setdefault(key, set()).add(point)

  if set(routed_cells) != expected:
    raise GraphLayoutError(
      "routed geometry does not cover every semantic edge"
    )

  for source, target in sorted(expected):
    points = routed_cells[(source, target)]
    source_place = placements[source]
    target_place = placements[target]
    source_anchor = (
      starts[source_place.column] + columns[source_place.column].width,
      source_place.row,
    )
    target_anchor = (
      starts[target_place.column] - 1,
      target_place.row,
    )
    if source_anchor not in points or target_anchor not in points:
      raise GraphLayoutError(
        "semantic edge route does not reach both endpoint anchors"
      )
    if not _is_connected(points):
      raise GraphLayoutError(
        "semantic edge route is not geometrically connected"
      )

  validate_rendered_reachability(
    validated,
    placements,
    columns,
    starts,
    cells,
    routed_cells,
  )

  for route in routes:
    source_column = placements[route.source].column
    target_column = placements[route.target].column
    expected_columns = tuple(range(source_column + 1, target_column))
    actual_columns = tuple(item.column for item in route.hidden)
    if actual_columns != expected_columns:
      raise GraphLayoutError("hidden continuation columns are incomplete")
    for item in route.hidden:
      if (
        item.semantic_source != route.source
        or item.semantic_target != route.target
      ):
        raise GraphLayoutError(
          "hidden continuation lost semantic endpoints"
        )


def _is_connected(points: set[tuple[int, int]]) -> bool:
  if not points:
    return False
  pending = {next(iter(points))}
  visited: set[tuple[int, int]] = set()
  while pending:
    point = pending.pop()
    if point in visited:
      continue
    visited.add(point)
    x, y = point
    for neighbour in (
      (x - 1, y),
      (x + 1, y),
      (x, y - 1),
      (x, y + 1),
    ):
      if neighbour in points and neighbour not in visited:
        pending.add(neighbour)
  return visited == points
