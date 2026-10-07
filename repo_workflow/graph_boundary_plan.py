from __future__ import annotations

from .graph_boundary_order import order_boundary_items
from .graph_routing import (
  bundle_item_key,
  dogleg_source_key,
  dogleg_target_key,
  edge_item_key,
)
from .graph_render_model import GraphSiblings, ValidatedGraph
from .graph_render_types import Column, Placement, SemanticEdge


def dogleg_edges(
  validated: ValidatedGraph,
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
) -> set[tuple[str, str]]:
  return {
    edge.key
    for edge in edges
    if (
      (edge.source_group, edge.target_group) not in bundle_relations
      and placements[edge.target].column == placements[edge.source].column + 1
      and placements[edge.source].row == placements[edge.target].row
      and len(validated.adjacency[edge.source]) > 1
      and len(validated.incoming[edge.target]) > 1
    )
  }


def bundle_relations(
  edges: tuple[SemanticEdge, ...],
  ranks: dict[GraphSiblings, int],
) -> set[tuple[GraphSiblings, GraphSiblings]]:
  grouped: dict[
    tuple[GraphSiblings, GraphSiblings],
    list[SemanticEdge],
  ] = {}
  for edge in edges:
    relation = edge.source_group, edge.target_group
    grouped.setdefault(relation, []).append(edge)

  result: set[tuple[GraphSiblings, GraphSiblings]] = set()
  for relation, relation_edges in grouped.items():
    source_group, target_group = relation
    if ranks[target_group] != ranks[source_group] + 1:
      continue
    if len(relation_edges) <= 1:
      continue
    lane_ids = {
      id(edge.lane)
      for edge in relation_edges
      if edge.lane is not None
    }
    if len(lane_ids) <= 1:
      result.add(relation)
  return result


def boundary_items(
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  validated: ValidatedGraph,
  ranks: dict[GraphSiblings, int],
  bundles: set[tuple[GraphSiblings, GraphSiblings]],
  doglegs: set[tuple[str, str]],
  dogleg_rows: dict[tuple[str, str], int],
) -> dict[int, tuple[tuple, ...]]:
  values: dict[int, set[tuple]] = {}
  bundled: set[tuple[str, str]] = set()
  for source_group, target_group in bundles:
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
    if edge.key in doglegs:
      values.setdefault(source.column, set()).update({
        dogleg_source_key(edge),
        dogleg_target_key(edge),
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
    boundary: order_boundary_items(
      values.get(boundary, set()),
      boundary,
      edges,
      placements,
      columns,
      validated,
      bundles,
      bundled,
      doglegs,
      dogleg_rows,
    )
    for boundary in range(max_column)
  }


def column_geometry(
  columns: dict[int, Column],
  items_by_boundary: dict[int, tuple[tuple, ...]],
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
    items = items_by_boundary.get(column, ())
    gap_width = max(3, len(items) + 2)
    gap_start = cursor + columns[column].width
    for item_index, item in enumerate(items):
      tracks[(column, item)] = gap_start + 1 + item_index
    cursor = gap_start + gap_width
  return starts, tracks
