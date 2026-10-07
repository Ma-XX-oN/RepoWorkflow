from __future__ import annotations

from .graph_geometry import long_route_candidate_valid
from .graph_long_routes import long_route_candidates
from .graph_render_model import ValidatedGraph
from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Column,
  Contribution,
  GraphLayoutError,
  HiddenContinuation,
  Placement,
  RouteRecord,
  SemanticEdge,
)
from .graph_routing import (
  dogleg_source_key,
  dogleg_target_key,
  route_long,
)


_MAX_STATES_PER_COMPONENT = 2048


def route_long_edges(
  edges: list[SemanticEdge],
  *,
  cells: dict[tuple[int, int], list[Contribution]],
  routes: list[RouteRecord],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
  long_bridges: set[tuple[str, str]] | frozenset[tuple[str, str]] = frozenset(),
) -> tuple[
  dict[tuple[int, int], list[Contribution]],
  list[RouteRecord],
]:
  current_cells = cells
  current_routes = routes
  current_used = {
    row: list(values)
    for row, values in used_rows.items()
  }

  for component in _geometric_components(
    tuple(edges),
    placements,
  ):
    current_cells, current_routes, current_used = _route_component(
      component,
      cells=current_cells,
      routes=current_routes,
      validated=validated,
      placements=placements,
      columns=columns,
      starts=starts,
      tracks=tracks,
      max_node_row=max_node_row,
      used_rows=current_used,
      long_bridges=long_bridges,
    )

  return current_cells, current_routes


def _route_component(
  edges: tuple[SemanticEdge, ...],
  *,
  cells: dict[tuple[int, int], list[Contribution]],
  routes: list[RouteRecord],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  max_node_row: int,
  used_rows: dict[int, list[SemanticEdge]],
  long_bridges: set[tuple[str, str]] | frozenset[tuple[str, str]],
) -> tuple[
  dict[tuple[int, int], list[Contribution]],
  list[RouteRecord],
  dict[int, list[SemanticEdge]],
]:
  states = 0
  relevant_used_rows = sum(
    1
    for values in used_rows.values()
    if any(
      _spans_overlap(
        _edge_span(candidate, placements),
        _edge_span(existing, placements),
      )
      for candidate in edges
      for existing in values
    )
  )
  fallback_rows = len(edges) + relevant_used_rows + 3

  def compatible_rows(
    edge: SemanticEdge,
    current_used: dict[int, list[SemanticEdge]],
  ) -> tuple[int, ...]:
    return long_route_candidates(
      edge,
      placements,
      max_node_row,
      current_used,
      lambda row: 0,
      fallback_rows=fallback_rows,
    )

  def search(
    remaining: tuple[SemanticEdge, ...],
    current_cells: dict[tuple[int, int], list[Contribution]],
    current_routes: list[RouteRecord],
    current_used: dict[int, list[SemanticEdge]],
  ):
    nonlocal states
    if not remaining:
      return current_cells, current_routes, current_used
    if states >= _MAX_STATES_PER_COMPONENT:
      raise GraphLayoutError(
        "bounded long-route component search exhausted "
        f"{_MAX_STATES_PER_COMPONENT} candidate states"
      )

    available_by_edge = {
      edge.key: compatible_rows(edge, current_used)
      for edge in remaining
    }
    if any(not rows for rows in available_by_edge.values()):
      return None

    edge = min(
      remaining,
      key=lambda item: (
        len(available_by_edge[item.key]),
        item.key,
      ),
    )
    source_item, target_item = _route_items(edge, long_bridges)
    candidates = long_route_candidates(
      edge,
      placements,
      max_node_row,
      current_used,
      lambda row: _crossing_cost(
        edge,
        row,
        current_cells,
        placements,
        columns,
        starts,
        tracks,
        source_item,
        target_item,
      ),
      fallback_rows=fallback_rows,
    )
    next_remaining = tuple(
      item
      for item in remaining
      if item is not edge
    )

    for row in candidates:
      states += 1
      if states > _MAX_STATES_PER_COMPONENT:
        raise GraphLayoutError(
          "bounded long-route component search exhausted "
          f"{_MAX_STATES_PER_COMPONENT} candidate states"
        )
      if not long_route_candidate_valid(
        edge,
        row,
        current_cells,
        current_routes,
        validated,
        placements,
        columns,
        starts,
        tracks,
        source_item=source_item,
        target_item=target_item,
      ):
        continue

      next_cells = {
        point: list(values)
        for point, values in current_cells.items()
      }
      route_long(
        next_cells,
        edge,
        placements,
        columns,
        starts,
        tracks,
        row,
        source_item=source_item,
        target_item=target_item,
      )
      source = placements[edge.source]
      target = placements[edge.target]
      hidden = tuple(
        HiddenContinuation(
          semantic_source=edge.source,
          semantic_target=edge.target,
          column=column,
          row=row,
        )
        for column in range(source.column + 1, target.column)
      )
      next_routes = [
        *current_routes,
        RouteRecord(edge.source, edge.target, "long", hidden),
      ]
      next_used = {
        used_row: list(values)
        for used_row, values in current_used.items()
      }
      next_used.setdefault(row, []).append(edge)

      if any(
        not compatible_rows(item, next_used)
        for item in next_remaining
      ):
        continue

      result = search(
        next_remaining,
        next_cells,
        next_routes,
        next_used,
      )
      if result is not None:
        return result
    return None

  result = search(edges, cells, routes, used_rows)
  if result is None:
    edge_text = ", ".join(
      f"{edge.source}->{edge.target}"
      for edge in edges
    )
    raise GraphLayoutError(
      "no semantically valid bounded long-route combination is available "
      f"for conflict component [{edge_text}]"
    )
  return result


def _geometric_components(
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
) -> tuple[tuple[SemanticEdge, ...], ...]:
  remaining = list(sorted(edges, key=lambda edge: edge.key))
  components: list[tuple[SemanticEdge, ...]] = []

  while remaining:
    seed = remaining.pop(0)
    component = [seed]
    pending = [seed]
    while pending:
      current = pending.pop()
      current_span = _edge_span(current, placements)
      connected = [
        edge
        for edge in remaining
        if _edges_conflict(
          current,
          edge,
          current_span,
          _edge_span(edge, placements),
        )
      ]
      for edge in connected:
        remaining.remove(edge)
        component.append(edge)
        pending.append(edge)
    components.append(tuple(sorted(component, key=lambda edge: edge.key)))

  return tuple(sorted(
    components,
    key=lambda component: component[0].key,
  ))


def _edges_conflict(
  left: SemanticEdge,
  right: SemanticEdge,
  left_span: tuple[int, int],
  right_span: tuple[int, int],
) -> bool:
  return (
    _spans_overlap(left_span, right_span)
    and left.source != right.source
    and left.target != right.target
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


def _route_items(
  edge: SemanticEdge,
  long_bridges: set[tuple[str, str]] | frozenset[tuple[str, str]],
) -> tuple[tuple | None, tuple | None]:
  if edge.key not in long_bridges:
    return None, None
  return dogleg_source_key(edge), dogleg_target_key(edge)


def _crossing_cost(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  source_item: tuple | None,
  target_item: tuple | None,
) -> int:
  proposed: dict[tuple[int, int], list[Contribution]] = {}
  route_long(
    proposed,
    edge,
    placements,
    columns,
    starts,
    tracks,
    row,
    source_item=source_item,
    target_item=target_item,
  )

  crossings = 0
  for point, new_items in proposed.items():
    old_items = cells.get(point, ())
    for new_item in new_items:
      for old_item in old_items:
        if _edges_can_join(new_item.edge, old_item.edge):
          continue
        new_horizontal = bool(new_item.bits & (_L | _R))
        new_vertical = bool(new_item.bits & (_U | _D))
        old_horizontal = bool(old_item.bits & (_L | _R))
        old_vertical = bool(old_item.bits & (_U | _D))
        if (
          (new_horizontal and old_vertical)
          or (new_vertical and old_horizontal)
        ):
          crossings += 1
  return crossings


def _edges_can_join(
  left: SemanticEdge,
  right: SemanticEdge,
) -> bool:
  return (
    left.source == right.source
    or left.target == right.target
  )
