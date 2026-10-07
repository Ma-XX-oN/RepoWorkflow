from __future__ import annotations

from .graph_geometry import edge_item_key
from .graph_ordering import group_key
from .graph_render_model import GraphSiblings, ValidatedGraph
from .graph_render_types import Column, Placement, SemanticEdge


def bundle_item_key(
  source: GraphSiblings,
  target: GraphSiblings,
) -> tuple:
  return "bundle", group_key(source), group_key(target)


def boundary_items(
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  ranks: dict[GraphSiblings, int],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
  bridge_edges: set[tuple[str, str]],
) -> dict[int, tuple[tuple, ...]]:
  values: dict[int, set[tuple]] = {}
  bundled: set[tuple[str, str]] = set()
  for source_group, target_group in bundle_relations:
    boundary = ranks[source_group]
    values.setdefault(boundary, set()).add(
      bundle_item_key(source_group, target_group)
    )
    for edge in edges:
      if (
        edge.source_group is source_group
        and edge.target_group is target_group
      ):
        bundled.add(edge.key)

  for edge in edges:
    if edge.key in bundled:
      continue
    source = placements[edge.source]
    target = placements[edge.target]
    if edge.key in bridge_edges:
      values.setdefault(source.column, set()).update({
        bridge_item_key(edge, "source"),
        bridge_item_key(edge, "target"),
      })
      continue
    values.setdefault(source.column, set()).add(
      edge_item_key(edge)
    )
    if target.column > source.column + 1:
      values.setdefault(target.column - 1, set()).add(
        edge_item_key(edge)
      )

  max_column = max(
    placement.column
    for placement in placements.values()
  )
  return {
    boundary: tuple(
      sorted(
        values.get(boundary, set()),
        key=lambda item: boundary_item_order(
          item,
          placements,
        ),
      )
    )
    for boundary in range(max_column)
  }


def boundary_item_order(
  item: tuple,
  placements: dict[str, Placement],
) -> tuple[int, int, tuple]:
  if item[0] == "bridge":
    direction = edge_direction(
      item[1],
      item[2],
      placements,
    )
    endpoint = 0 if item[3] == "source" else 2
    return direction, endpoint, item
  if item[0] != "edge":
    return 1, 1, item
  return (
    edge_direction(item[1], item[2], placements),
    1,
    item,
  )


def edge_direction(
  source: str,
  target: str,
  placements: dict[str, Placement],
) -> int:
  delta = placements[target].row - placements[source].row
  if delta < 0:
    return 0
  if delta > 0:
    return 2
  return 1


def bridge_item_key(
  edge: SemanticEdge,
  endpoint: str,
) -> tuple:
  return "bridge", edge.source, edge.target, endpoint


def bridge_edges(
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  validated: ValidatedGraph,
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
) -> set[tuple[str, str]]:
  result: set[tuple[str, str]] = set()
  for edge in edges:
    if (
      (edge.source_group, edge.target_group)
      in bundle_relations
    ):
      continue
    source = placements[edge.source]
    target = placements[edge.target]
    if target.column != source.column + 1:
      continue
    if (
      len(validated.adjacency[edge.source]) > 1
      and len(validated.incoming[edge.target]) > 1
    ):
      result.add(edge.key)
  return result


def column_geometry(
  columns: dict[int, Column],
  boundary_items: dict[int, tuple[tuple, ...]],
) -> tuple[
  dict[int, int],
  dict[tuple[int, tuple], int],
]:
  starts: dict[int, int] = {}
  tracks: dict[tuple[int, tuple], int] = {}
  cursor = 0
  ordered_columns = sorted(columns)
  for index, column in enumerate(ordered_columns):
    starts[column] = cursor
    if index == len(ordered_columns) - 1:
      continue
    items = boundary_items.get(column, ())
    gap_width = max(3, len(items) + 2)
    gap_start = cursor + columns[column].width
    for item_index, item in enumerate(items):
      tracks[(column, item)] = gap_start + 1 + item_index
    cursor = gap_start + gap_width
  return starts, tracks


