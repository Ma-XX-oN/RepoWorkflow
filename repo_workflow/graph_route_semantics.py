from __future__ import annotations

from .graph_render_model import ValidatedGraph
from .graph_route_interactions import (
  interaction_component,
  switch_edges_for_cell,
)
from .graph_route_path import (
  collect_routed_edge_bits,
  simple_path,
)
from .graph_routing import route_long
from .graph_render_types import (
  Column,
  Contribution,
  GraphLayoutError,
  Placement,
  RouteRecord,
  SemanticEdge,
)


def validate_route_candidate_reachability(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  expected: set[tuple[str, str]],
) -> None:
  routed_cells = collect_routed_edge_bits(cells)
  unexpected = set(routed_cells) - expected
  if unexpected:
    raise GraphLayoutError(
      "candidate geometry contains unexpected semantic edges "
      + ", ".join(repr(item) for item in sorted(unexpected))
    )

  missing = expected - set(routed_cells)
  if missing:
    raise GraphLayoutError(
      "candidate geometry is missing semantic edges "
      + ", ".join(repr(item) for item in sorted(missing))
    )

  for source, target in expected:
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
        f"candidate route {source!r} -> {target!r} "
        "does not reach both endpoint anchors"
      )
    simple_path(route_bits, source_anchor, target_anchor)

  expected_by_source: dict[str, set[str]] = {}
  for source, target in expected:
    expected_by_source.setdefault(source, set()).add(target)
  validate_rendered_reachability(
    validated,
    placements,
    columns,
    starts,
    cells,
    routed_cells,
    expected_by_source=expected_by_source,
  )


def route_candidate_preserves_reachability(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  expected: set[tuple[str, str]],
) -> bool:
  try:
    validate_route_candidate_reachability(
      validated,
      placements,
      columns,
      starts,
      cells,
      expected,
    )
  except GraphLayoutError:
    return False
  return True


def _long_route_candidate_geometry(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  *,
  source_item: tuple | None = None,
  target_item: tuple | None = None,
) -> tuple[
  dict[tuple[int, int], list[Contribution]],
  set[tuple[str, str]],
]:
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
    source_item=source_item,
    target_item=target_item,
  )
  component = interaction_component(
    candidate_cells,
    edge.key,
  )
  local_cells = {
    point: [
      contribution
      for contribution in contributions
      if contribution.edge.key in component
    ]
    for point, contributions in candidate_cells.items()
    if any(
      contribution.edge.key in component
      for contribution in contributions
    )
  }
  return local_cells, component


def validate_long_route_candidate(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  *,
  source_item: tuple | None = None,
  target_item: tuple | None = None,
) -> None:
  local_cells, component = _long_route_candidate_geometry(
    edge,
    row,
    cells,
    placements,
    columns,
    starts,
    tracks,
    source_item=source_item,
    target_item=target_item,
  )
  validate_route_candidate_reachability(
    validated,
    placements,
    columns,
    starts,
    local_cells,
    component,
  )


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
  *,
  source_item: tuple | None = None,
  target_item: tuple | None = None,
) -> bool:
  try:
    validate_long_route_candidate(
      edge,
      row,
      cells,
      validated,
      placements,
      columns,
      starts,
      tracks,
      source_item=source_item,
      target_item=target_item,
    )
  except GraphLayoutError:
    return False
  return True


def validate_rendered_reachability(
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  cells: dict[tuple[int, int], list[Contribution]],
  routed_cells: dict[
    tuple[str, str],
    dict[tuple[int, int], int],
  ],
  *,
  expected_by_source: dict[str, set[str]] | None = None,
) -> None:
  paths: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}
  indices: dict[
    tuple[str, str],
    dict[tuple[int, int], int],
  ] = {}
  for edge, route_bits in routed_cells.items():
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
    path = simple_path(route_bits, source_anchor, target_anchor)
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
    switch_edges = _switch_edges(tuple(edge_map.values()))
    if switch_edges:
      switches[point] = switch_edges

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
    trace: dict[
      tuple[tuple[str, str], tuple[int, int]],
      tuple[str, ...],
    ] = {}
    for target in sorted(expected_targets):
      edge = source, target
      state = edge, paths[edge][0]
      pending.append(state)
      trace[state] = ()

    visited: set[
      tuple[tuple[str, str], tuple[int, int]]
    ] = set()
    reached: set[str] = set()
    unexpected_trace: dict[str, tuple[str, ...]] = {}

    while pending:
      edge, point = pending.pop()
      state = edge, point
      if state in visited:
        continue
      visited.add(state)

      current_trace = trace.get(state, ())
      path = paths[edge]
      index = indices[edge][point]
      if index == len(path) - 1:
        reached.add(edge[1])
        if edge[1] not in expected_targets:
          unexpected_trace.setdefault(edge[1], current_trace)
      else:
        next_state = edge, path[index + 1]
        if next_state not in trace:
          trace[next_state] = current_trace
        pending.append(next_state)

      for other in switches.get(point, set()):
        if other == edge or point not in indices[other]:
          continue
        next_state = other, point
        if next_state not in trace:
          trace[next_state] = (
            *current_trace,
            (
              f"{edge[0]}->{edge[1]} => "
              f"{other[0]}->{other[1]} at {point}"
            ),
          )
        pending.append(next_state)

    if reached != expected_targets:
      unexpected = sorted(reached - expected_targets)
      detail = ""
      if unexpected:
        target = unexpected[0]
        steps = unexpected_trace.get(target, ())
        if steps:
          detail = "; switch trace: " + " | ".join(steps)
      raise GraphLayoutError(
        "rendered directed geometry changes semantic reachability "
        f"for {source!r}: expected {sorted(expected_targets)!r}, "
        f"got {sorted(reached)!r}{detail}"
      )
