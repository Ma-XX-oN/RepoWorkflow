from __future__ import annotations

from .graph_render_model import ValidatedGraph
from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Column,
  Contribution,
  GraphLayoutError,
  Placement,
  RouteRecord,
  SemanticEdge,
)


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


def edge_item_key(edge: SemanticEdge) -> tuple:
  return "edge", edge.source, edge.target


def route_candidate_preserves_reachability(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  expected: set[tuple[str, str]],
) -> bool:
  routed_cells: dict[
    tuple[str, str],
    set[tuple[int, int]],
  ] = {}
  for point, contributions in cells.items():
    for contribution in contributions:
      key = contribution.edge.key
      if key not in expected:
        return False
      routed_cells.setdefault(key, set()).add(point)

  if set(routed_cells) != expected:
    return False

  for source, target in expected:
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
      return False
    try:
      _simple_path(points, source_anchor, target_anchor)
    except GraphLayoutError:
      return False

  expected_by_source: dict[str, set[str]] = {}
  for source, target in expected:
    expected_by_source.setdefault(source, set()).add(target)
  try:
    _validate_rendered_reachability(
      validated,
      placements,
      columns,
      starts,
      cells,
      routed_cells,
      expected_by_source=expected_by_source,
    )
  except GraphLayoutError:
    return False
  return True


def long_route_candidate_valid(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  routes: list[RouteRecord],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
) -> bool:
  candidate_cells = {
    point: list(values)
    for point, values in cells.items()
  }
  route_long(
    candidate_cells,
    edge,
    placements,
    columns,
    starts,
    tracks,
    row,
  )
  expected = {
    (route.source, route.target)
    for route in routes
  }
  expected.add(edge.key)
  return route_candidate_preserves_reachability(
    validated,
    placements,
    columns,
    starts,
    candidate_cells,
    expected,
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

  _validate_rendered_reachability(
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


def _validate_rendered_reachability(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  routed_cells: dict[tuple[str, str], set[tuple[int, int]]],
  *,
  expected_by_source: dict[str, set[str]] | None = None,
) -> None:
  paths: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}
  indices: dict[
    tuple[str, str],
    dict[tuple[int, int], int],
  ] = {}
  for edge, points in routed_cells.items():
    source, target = edge
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
    path = _simple_path(points, source_anchor, target_anchor)
    paths[edge] = path
    indices[edge] = {
      point: index
      for index, point in enumerate(path)
    }

  switches: dict[
    tuple[int, int],
    set[tuple[str, str]],
  ] = {}
  for point, contributions in cells.items():
    edge_map = {
      contribution.edge.key: contribution
      for contribution in contributions
    }
    if len(edge_map) < 2:
      continue
    values = list(edge_map.values())
    same_source = len({
      item.edge.source
      for item in values
    }) == 1
    same_target = len({
      item.edge.target
      for item in values
    }) == 1
    bundles = {
      item.bundle
      for item in values
    }
    same_bundle = len(bundles) == 1 and None not in bundles
    if same_source or same_target or same_bundle:
      switches[point] = set(edge_map)

  if expected_by_source is None:
    expected_by_source = {
      source: set(targets)
      for source, targets in validated.adjacency.items()
    }
  for source, expected_targets in expected_by_source.items():
    if not expected_targets:
      continue
    pending: list[
      tuple[tuple[str, str], tuple[int, int]]
    ] = []
    for target in sorted(expected_targets):
      edge = source, target
      pending.append((edge, paths[edge][0]))

    visited: set[
      tuple[tuple[str, str], tuple[int, int]]
    ] = set()
    reached: set[str] = set()
    while pending:
      edge, point = pending.pop()
      state = edge, point
      if state in visited:
        continue
      visited.add(state)

      path = paths[edge]
      index = indices[edge][point]
      if index == len(path) - 1:
        reached.add(edge[1])
      else:
        pending.append((edge, path[index + 1]))

      for other in switches.get(point, set()):
        if other == edge or point not in indices[other]:
          continue
        pending.append((other, point))

    if reached != expected_targets:
      raise GraphLayoutError(
        "rendered directed geometry changes semantic reachability "
        f"for {source!r}: expected {sorted(expected_targets)!r}, "
        f"got {sorted(reached)!r}"
      )


def _simple_path(
  points: set[tuple[int, int]],
  source: tuple[int, int],
  target: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
  neighbours: dict[
    tuple[int, int],
    list[tuple[int, int]],
  ] = {}
  for x, y in points:
    neighbours[(x, y)] = [
      point
      for point in (
        (x - 1, y),
        (x + 1, y),
        (x, y - 1),
        (x, y + 1),
      )
      if point in points
    ]
  if any(len(values) > 2 for values in neighbours.values()):
    raise GraphLayoutError(
      "one semantic edge route branches or self-intersects"
    )

  path = [source]
  previous = None
  current = source
  while current != target:
    choices = [
      point
      for point in neighbours[current]
      if point != previous
    ]
    if len(choices) != 1:
      raise GraphLayoutError(
        "semantic edge route is not one simple path"
      )
    previous, current = current, choices[0]
    path.append(current)
    if len(path) > len(points):
      raise GraphLayoutError("semantic edge route contains a loop")

  if len(path) != len(points):
    raise GraphLayoutError(
      "semantic edge route contains geometry outside its endpoint path"
    )
  return tuple(path)


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
