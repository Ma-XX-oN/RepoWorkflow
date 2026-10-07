from __future__ import annotations

from collections import deque

from .graph_geometry import route_candidate_preserves_reachability
from .graph_routing import (
  dogleg_source_key,
  dogleg_target_key,
  edge_item_key,
  route_adjacent,
  route_adjacent_dogleg,
)
from .graph_ordering import group_key
from .graph_render_model import GraphSiblings, ValidatedGraph
from .graph_render_types import (
  Column,
  GraphLayoutError,
  Placement,
  SemanticEdge,
)


_MAX_CANDIDATES = 4096


def order_boundary_items(
  items: set[tuple],
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  validated: ValidatedGraph,
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bundled: set[tuple[str, str]],
  dogleg_edges: set[tuple[str, str]],
  dogleg_rows: dict[tuple[str, str], int],
) -> tuple[tuple, ...]:
  base = tuple(
    sorted(
      items,
      key=lambda item: _item_order(item, placements),
    )
  )
  if _order_is_valid(
    base,
    boundary,
    edges,
    placements,
    columns,
    validated,
    bundle_relations,
    bundled,
    dogleg_edges,
    dogleg_rows,
  ):
    return base

  pending = deque([base])
  seen = {base}
  checked = 1
  while pending and checked < _MAX_CANDIDATES:
    current = pending.popleft()
    for index in range(len(current) - 1):
      candidate = list(current)
      candidate[index], candidate[index + 1] = (
        candidate[index + 1],
        candidate[index],
      )
      ordered = tuple(candidate)
      if ordered in seen:
        continue
      seen.add(ordered)
      checked += 1
      if _order_is_valid(
        ordered,
        boundary,
        edges,
        placements,
        columns,
        validated,
        bundle_relations,
        bundled,
        dogleg_edges,
    dogleg_rows,
  ):
        return ordered
      if checked >= _MAX_CANDIDATES:
        break
      pending.append(ordered)

  raise GraphLayoutError(
    "no semantically valid bounded adjacent-track ordering is available"
  )


def _order_is_valid(
  order: tuple[tuple, ...],
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  validated: ValidatedGraph,
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bundled: set[tuple[str, str]],
  dogleg_edges: set[tuple[str, str]],
  dogleg_rows: dict[tuple[str, str], int],
) -> bool:
  gap_width = max(3, len(order) + 2)
  source_start = 0
  target_start = columns[boundary].width + gap_width
  starts = {
    boundary: source_start,
    boundary + 1: target_start,
  }
  tracks = {
    item: columns[boundary].width + 1 + index
    for index, item in enumerate(order)
  }
  cells = {}
  expected: set[tuple[str, str]] = set()

  for source_group, target_group in sorted(
    bundle_relations,
    key=lambda item: (
      group_key(item[0]),
      group_key(item[1]),
    ),
  ):
    relation_edges = tuple(
      edge
      for edge in edges
      if (
        edge.source_group is source_group
        and edge.target_group is target_group
        and placements[edge.source].column == boundary
        and placements[edge.target].column == boundary + 1
      )
    )
    if not relation_edges:
      continue
    item = _bundle_item_key(source_group, target_group)
    if item not in tracks:
      continue
    x = tracks[item]
    bundle_id = (id(source_group), id(target_group))
    for edge in relation_edges:
      route_adjacent(
        cells,
        edge,
        placements,
        columns,
        starts,
        x,
        bundle=bundle_id,
      )
      expected.add(edge.key)

  for edge in edges:
    if edge.key in bundled:
      continue
    source = placements[edge.source]
    target = placements[edge.target]
    if (
      source.column != boundary
      or target.column != boundary + 1
    ):
      continue
    if edge.key in dogleg_edges:
      source_item = dogleg_source_key(edge)
      target_item = dogleg_target_key(edge)
      if source_item not in tracks or target_item not in tracks:
        return False
      route_adjacent_dogleg(
        cells,
        edge,
        placements,
        columns,
        starts,
        tracks[source_item],
        tracks[target_item],
        dogleg_rows[edge.key],
      )
    else:
      item = edge_item_key(edge)
      if item not in tracks:
        return False
      route_adjacent(
        cells,
        edge,
        placements,
        columns,
        starts,
        tracks[item],
      )
    expected.add(edge.key)

  if not expected:
    return True
  return route_candidate_preserves_reachability(
    validated,
    placements,
    columns,
    starts,
    cells,
    expected,
  )


def _bundle_item_key(
  source: GraphSiblings,
  target: GraphSiblings,
) -> tuple:
  return "bundle", group_key(source), group_key(target)


def _item_order(
  item: tuple,
  placements: dict[str, Placement],
) -> tuple[int, tuple]:
  if item[0] == "dogleg-source":
    return -1, item
  if item[0] == "dogleg-target":
    return 3, item
  if item[0] != "edge":
    return 1, item
  source = placements[item[1]]
  target = placements[item[2]]
  delta = target.row - source.row
  if delta < 0:
    direction = 0
  elif delta > 0:
    direction = 2
  else:
    direction = 1
  return direction, item
