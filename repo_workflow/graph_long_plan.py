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
  private_base = max(
    [max_node_row, *current_used.keys()],
    default=max_node_row,
  ) + 1

  for private_index, edge in enumerate(sorted(edges, key=lambda item: item.key)):
    private_row = private_base + private_index
    source_item, target_item = _route_items(edge, long_bridges)
    candidates = list(long_route_candidates(
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
      fallback_rows=1,
    ))
    candidates = [
      row
      for row in candidates
      if row < private_base
    ]
    candidates.append(private_row)

    chosen = None
    for row in candidates:
      if long_route_candidate_valid(
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
        chosen = row
        break

    if chosen is None:
      raise GraphLayoutError(
        "no semantically valid long-route candidate is available for "
        f"{edge.source!r} -> {edge.target!r}, including private row "
        f"{private_row}"
      )

    route_long(
      current_cells,
      edge,
      placements,
      columns,
      starts,
      tracks,
      chosen,
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
        row=chosen,
      )
      for column in range(source.column + 1, target.column)
    )
    current_routes.append(
      RouteRecord(edge.source, edge.target, "long", hidden)
    )
    current_used.setdefault(chosen, []).append(edge)

  return current_cells, current_routes


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
