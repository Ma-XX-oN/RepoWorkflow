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


_MAX_STATES = 8192


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

  for component in _geometric_components(edges, placements):
    current_cells, current_routes, current_used = _route_component(
      component,
      cells=current_cells,
      routes=current_routes,
      used_rows=current_used,
      validated=validated,
      placements=placements,
      columns=columns,
      starts=starts,
      tracks=tracks,
      max_node_row=max_node_row,
      long_bridges=long_bridges,
    )

  return current_cells, current_routes


def _route_component(
  edges: tuple[SemanticEdge, ...],
  *,
  cells: dict[tuple[int, int], list[Contribution]],
  routes: list[RouteRecord],
  used_rows: dict[int, list[SemanticEdge]],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  max_node_row: int,
  long_bridges: set[tuple[str, str]] | frozenset[tuple[str, str]],
) -> tuple[
  dict[tuple[int, int], list[Contribution]],
  list[RouteRecord],
  dict[int, list[SemanticEdge]],
]:
  states = 0
  fallback_rows = len(edges) + len(used_rows) + 3

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
    if states >= _MAX_STATES:
      raise GraphLayoutError(
        "bounded long-route search exhausted "
        f"{_MAX_STATES} candidate states"
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
      if states > _MAX_STATES:
        raise GraphLayoutError(
          "bounded long-route search exhausted "
          f"{_MAX_STATES} candidate states"
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
      f"for [{edge_text}]"
    )
  return result


def _geometric_components(
  edges: list[SemanticEdge],
  placements: dict[str, Placement],
) -> tuple[tuple[SemanticEdge, ...], ...]:
  remaining = set(edge.key for edge in edges)
  edge_by_key = {edge.key: edge for edge in edges}
  result: list[tuple[SemanticEdge, ...]] = []

  while remaining:
    start = min(remaining)
    pending = [start]
    component: set[tuple[str, str]] = set()
    while pending:
      key = pending.pop()
      if key in component:
        continue
      component.add(key)
      remaining.discard(key)
      span = _edge_span(edge_by_key[key], placements)
      connected = [
        other
        for other in sorted(remaining)
        if _spans_overlap(
          span,
          _edge_span(edge_by_key[other], placements),
        )
      ]
      pending.extend(connected)
    result.append(tuple(
      edge_by_key[key]
      for key in sorted(component)
    ))

  return tuple(result)


def _edge_span(
  edge: SemanticEdge,
  placements: dict[str, Placement],
) -> tuple[int, int]:
  return (
    placements[edge.source].column,
    placements[edge.target].column - 1,
  )


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
