from __future__ import annotations

from collections import deque

from .graph_route_semantics import (
  route_candidate_preserves_reachability,
  validate_route_candidate_reachability,
)
from .graph_routing import (
  bundle_item_key,
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
  active = _active_items(
    boundary,
    edges,
    placements,
    bundle_relations,
    bundled,
    dogleg_edges,
  )
  active_base = tuple(
    item
    for item in base
    if item in active
  )
  base_errors: list[str] = []
  best_order: tuple[tuple, ...] | None = None
  best_score: tuple | None = None

  def consider(
    active_order: tuple[tuple, ...],
    *,
    errors: list[str] | None = None,
  ) -> None:
    nonlocal best_order, best_score
    if not _order_is_valid(
      active_order,
      boundary,
      edges,
      placements,
      columns,
      validated,
      bundle_relations,
      bundled,
      dogleg_edges,
      dogleg_rows,
      errors=errors,
    ):
      return
    full_order = _merge_passive(base, active_order, active)
    score = (
      *_boundary_order_quality(
        full_order,
        boundary,
        edges,
        placements,
        columns,
        bundle_relations,
        bundled,
        dogleg_edges,
        dogleg_rows,
      ),
      full_order,
    )
    if best_score is None or score < best_score:
      best_score = score
      best_order = full_order

  consider(active_base, errors=base_errors)
  if len(active_base) <= 1:
    if best_order is not None:
      return best_order
  else:
    pending = deque([active_base])
    seen = {active_base}
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
        consider(ordered)
        if checked >= _MAX_CANDIDATES:
          break
        pending.append(ordered)

  if best_order is not None:
    return best_order

  adjacent_edges = tuple(
    edge.key
    for edge in edges
    if (
      placements[edge.source].column == boundary
      and placements[edge.target].column == boundary + 1
    )
  )
  checked = len(seen) if len(active_base) > 1 else 1
  raise GraphLayoutError(
    "no semantically valid bounded adjacent-track ordering is available "
    f"for boundary {boundary} after {checked} active candidates; "
    f"active_items={active_base!r}; passive_count={len(base) - len(active_base)}; "
    f"edges={adjacent_edges!r}; "
    f"base_error={base_errors[0] if base_errors else 'unknown'}"
  )


def _active_items(
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bundled: set[tuple[str, str]],
  dogleg_edges: set[tuple[str, str]],
) -> set[tuple]:
  result: set[tuple] = set()

  for source_group, target_group in bundle_relations:
    if any(
      (
        edge.source_group is source_group
        and edge.target_group is target_group
        and placements[edge.source].column == boundary
        and placements[edge.target].column == boundary + 1
      )
      for edge in edges
    ):
      result.add(bundle_item_key(source_group, target_group))

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
      result.add(dogleg_source_key(edge))
      result.add(dogleg_target_key(edge))
    else:
      result.add(edge_item_key(edge))

  return result


def _merge_passive(
  base: tuple[tuple, ...],
  active_order: tuple[tuple, ...],
  active: set[tuple],
) -> tuple[tuple, ...]:
  result = list(base)
  positions = [
    index
    for index, item in enumerate(base)
    if item in active
  ]
  if len(positions) != len(active_order):
    raise GraphLayoutError(
      "adjacent-track active/passive partition is inconsistent"
    )
  for index, item in zip(positions, active_order):
    result[index] = item
  return tuple(result)



def _boundary_order_quality(
  order: tuple[tuple, ...],
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bundled: set[tuple[str, str]],
  dogleg_edges: set[tuple[str, str]],
  dogleg_rows: dict[tuple[str, str], int],
) -> tuple[int, int, int]:
  cells, _ = _order_cells(
    order,
    boundary,
    edges,
    placements,
    columns,
    bundle_relations,
    bundled,
    dogleg_edges,
    dogleg_rows,
  )

  directions: dict[tuple[int, int], set[int]] = {}
  for point, contributions in cells.items():
    for contribution in contributions:
      if contribution.vertical_direction:
        directions.setdefault(point, set()).add(
          contribution.vertical_direction
        )

  opposing = 0
  adjacent_verticals = 0
  for (x, y), values in directions.items():
    right = directions.get((x + 1, y), set())
    if not right:
      continue
    adjacent_verticals += 1
    if (
      (1 in values and -1 in right)
      or (-1 in values and 1 in right)
    ):
      opposing += 1

  crossings = 0
  for contributions in cells.values():
    per_edge: dict[tuple[str, str], int] = {}
    for contribution in contributions:
      key = contribution.edge.key
      per_edge[key] = (
        per_edge.get(key, 0)
        | contribution.bits
      )
    if len(per_edge) < 2:
      continue
    has_horizontal = any(
      bits & 3
      for bits in per_edge.values()
    )
    has_vertical = any(
      bits & 12
      for bits in per_edge.values()
    )
    if has_horizontal and has_vertical:
      crossings += 1

  return opposing, adjacent_verticals, crossings


def _order_cells(
  order: tuple[tuple, ...],
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bundled: set[tuple[str, str]],
  dogleg_edges: set[tuple[str, str]],
  dogleg_rows: dict[tuple[str, str], int],
) -> tuple[
  dict[tuple[int, int], list],
  set[tuple[str, str]],
]:
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
    item = bundle_item_key(source_group, target_group)
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
        return {}, set()
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
        return {}, set()
      route_adjacent(
        cells,
        edge,
        placements,
        columns,
        starts,
        tracks[item],
      )
    expected.add(edge.key)

  return cells, expected


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
  *,
  errors: list[str] | None = None,
) -> bool:
  cells, expected = _order_cells(
    order,
    boundary,
    edges,
    placements,
    columns,
    bundle_relations,
    bundled,
    dogleg_edges,
    dogleg_rows,
  )
  gap_width = max(3, len(order) + 2)
  starts = {
    boundary: 0,
    boundary + 1: columns[boundary].width + gap_width,
  }
  if not expected:
    return True
  if errors is None:
    return route_candidate_preserves_reachability(
      validated,
      placements,
      columns,
      starts,
      cells,
      expected,
    )
  try:
    validate_route_candidate_reachability(
      validated,
      placements,
      columns,
      starts,
      cells,
      expected,
    )
  except GraphLayoutError as error:
    errors.append(str(error))
    return False
  return True


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
