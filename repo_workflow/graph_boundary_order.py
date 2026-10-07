from __future__ import annotations

from .graph_render_types import (
  GraphLayoutError,
  Placement,
  SemanticEdge,
)


def order_boundary_items(
  items: set[tuple],
  boundary: int,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  bundled: set[tuple[str, str]],
) -> tuple[tuple, ...]:
  constraints = {
    item: set()
    for item in items
  }
  adjacent = [
    edge
    for edge in edges
    if (
      edge.key not in bundled
      and placements[edge.source].column == boundary
      and placements[edge.target].column == boundary + 1
    )
  ]
  by_source: dict[str, list[SemanticEdge]] = {}
  by_target: dict[str, list[SemanticEdge]] = {}
  for edge in adjacent:
    by_source.setdefault(edge.source, []).append(edge)
    by_target.setdefault(edge.target, []).append(edge)

  for bridge in adjacent:
    outgoing = [
      edge
      for edge in by_source[bridge.source]
      if edge.key != bridge.key
    ]
    incoming = [
      edge
      for edge in by_target[bridge.target]
      if edge.key != bridge.key
    ]
    for source_edge in outgoing:
      source_item = _edge_item(source_edge)
      if source_item not in constraints:
        continue
      for target_edge in incoming:
        target_item = _edge_item(target_edge)
        if target_item not in constraints:
          continue
        constraints[source_item].add(target_item)

  indegree = {item: 0 for item in items}
  for targets in constraints.values():
    for target in targets:
      indegree[target] += 1

  ready = sorted(
    (item for item, degree in indegree.items() if degree == 0),
    key=lambda item: _item_order(item, placements),
  )
  ordered: list[tuple] = []
  while ready:
    item = ready.pop(0)
    ordered.append(item)
    for target in sorted(
      constraints[item],
      key=lambda value: _item_order(value, placements),
    ):
      indegree[target] -= 1
      if indegree[target] == 0:
        ready.append(target)
        ready.sort(key=lambda value: _item_order(value, placements))

  if len(ordered) != len(items):
    raise GraphLayoutError(
      "adjacent track ordering constraints are cyclic"
    )
  return tuple(ordered)


def _edge_item(edge: SemanticEdge) -> tuple:
  return "edge", edge.source, edge.target


def _item_order(
  item: tuple,
  placements: dict[str, Placement],
) -> tuple[int, tuple]:
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
