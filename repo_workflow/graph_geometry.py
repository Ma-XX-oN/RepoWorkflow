from __future__ import annotations

from .graph_render_model import ValidatedGraph
from .graph_route_semantics import (
  long_route_candidate_valid,
  route_candidate_preserves_reachability,
  collect_routed_edge_bits,
  simple_path,
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

  routed_cells = collect_routed_edge_bits(cells)
  if set(routed_cells) - expected:
    raise GraphLayoutError(
      "routed geometry contains an unknown semantic edge"
    )

  if set(routed_cells) != expected:
    raise GraphLayoutError(
      "routed geometry does not cover every semantic edge"
    )

  for source, target in sorted(expected):
    route_bits = routed_cells[(source, target)]
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
    if source_anchor not in route_bits or target_anchor not in route_bits:
      raise GraphLayoutError(
        "semantic edge route does not reach both endpoint anchors"
      )
    simple_path(route_bits, source_anchor, target_anchor)

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
