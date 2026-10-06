from __future__ import annotations

from .graph_geometry import (
  edge_item_key,
  route_adjacent,
  route_long,
  validate_routes,
)
from .graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphInputError,
  GraphSiblings,
  ValidatedGraph,
  validate_graph,
)
from .graph_render_types import (
  Column,
  Contribution,
  HiddenContinuation,
  LayoutPlan,
  NodeToken,
  Placement,
  RouteRecord,
  SemanticEdge,
)


def build_layout(graph: Graph) -> LayoutPlan:
  validated = validate_graph(graph)
  if not validated.node_group:
    return LayoutPlan(0, -1, {}, {}, (), graph.default_edge_colour)

  group_rank = _group_ranks(graph.siblings)
  placements, column_nodes, max_node_row = _place_nodes(
    graph.siblings,
    group_rank,
  )
  columns = _format_columns(validated, column_nodes)
  edges = _semantic_edges(validated)

  bundle_relations = _bundle_relations(edges, group_rank)
  boundary_items = _boundary_items(
    edges,
    placements,
    group_rank,
    bundle_relations,
  )
  column_start, track_x = _column_geometry(columns, boundary_items)

  cells: dict[tuple[int, int], list[Contribution]] = {}
  routes: list[RouteRecord] = []
  long_index = 0
  bundled_edges: set[tuple[str, str]] = set()

  for relation in sorted(
    bundle_relations,
    key=lambda item: (
      _group_key(item[0]),
      _group_key(item[1]),
    ),
  ):
    source_group, target_group = relation
    relation_edges = tuple(
      edge
      for edge in edges
      if edge.source_group is source_group
      and edge.target_group is target_group
    )
    if not relation_edges:
      continue
    boundary = group_rank[source_group]
    item_key = _bundle_item_key(source_group, target_group)
    x = track_x[(boundary, item_key)]
    bundle_id = (id(source_group), id(target_group))
    for edge in relation_edges:
      route_adjacent(
        cells,
        edge,
        placements,
        columns,
        column_start,
        x,
        bundle=bundle_id,
      )
      bundled_edges.add(edge.key)
      routes.append(
        RouteRecord(edge.source, edge.target, "bundle", ())
      )

  for edge in edges:
    if edge.key in bundled_edges:
      continue
    source = placements[edge.source]
    target = placements[edge.target]
    span = target.column - source.column
    if span <= 0:
      raise ValueError(
        "semantic edge does not point to a later column"
      )
    if span == 1:
      boundary = source.column
      item_key = edge_item_key(edge)
      x = track_x[(boundary, item_key)]
      route_adjacent(
        cells,
        edge,
        placements,
        columns,
        column_start,
        x,
      )
      routes.append(
        RouteRecord(edge.source, edge.target, "adjacent", ())
      )
      continue

    track_y = max_node_row + 2 + long_index * 2
    long_index += 1
    hidden = tuple(
      HiddenContinuation(
        semantic_source=edge.source,
        semantic_target=edge.target,
        column=column,
        row=track_y,
      )
      for column in range(source.column + 1, target.column)
    )
    route_long(
      cells,
      edge,
      placements,
      columns,
      column_start,
      track_x,
      track_y,
    )
    routes.append(
      RouteRecord(edge.source, edge.target, "long", hidden)
    )

  ordered_routes = tuple(
    sorted(routes, key=lambda route: (route.source, route.target))
  )
  validate_routes(validated, placements, ordered_routes)

  max_y = max(
    [max_node_row]
    + [point[1] for point in cells]
    + [
      continuation.row
      for route in ordered_routes
      for continuation in route.hidden
    ]
  )
  width = max(
    column_start[index] + columns[index].width
    for index in columns
  )
  node_tokens = _node_tokens(
    column_nodes,
    columns,
    placements,
    column_start,
  )
  return LayoutPlan(
    width=width,
    max_y=max_y,
    node_tokens=node_tokens,
    cells=cells,
    routes=ordered_routes,
    default_colour=graph.default_edge_colour,
  )


def _group_key(group: GraphSiblings) -> tuple[str, ...]:
  return tuple(sorted(group.nodes))


def _group_ranks(
  groups: tuple[GraphSiblings, ...],
) -> dict[GraphSiblings, int]:
  incoming: dict[GraphSiblings, set[GraphSiblings]] = {
    group: set() for group in groups
  }
  for group in groups:
    for target in group.to_nodes:
      incoming[target].add(group)

  indegree = {group: len(incoming[group]) for group in groups}
  ready = sorted(
    (group for group in groups if indegree[group] == 0),
    key=_group_key,
  )
  ranks = {group: 0 for group in ready}
  seen: list[GraphSiblings] = []
  while ready:
    group = ready.pop(0)
    seen.append(group)
    for target in sorted(group.to_nodes, key=_group_key):
      ranks[target] = max(
        ranks.get(target, 0),
        ranks[group] + 1,
      )
      indegree[target] -= 1
      if indegree[target] == 0:
        ready.append(target)
        ready.sort(key=_group_key)
  if len(seen) != len(groups):
    raise ValueError(
      "validated graph unexpectedly contains a cycle"
    )
  return ranks


def _place_nodes(
  groups: tuple[GraphSiblings, ...],
  ranks: dict[GraphSiblings, int],
) -> tuple[
  dict[str, Placement],
  dict[int, tuple[str, ...]],
  int,
]:
  by_column: dict[int, list[GraphSiblings]] = {}
  for group in groups:
    by_column.setdefault(ranks[group], []).append(group)

  placements: dict[str, Placement] = {}
  column_nodes: dict[int, tuple[str, ...]] = {}
  max_row = 0
  for column in sorted(by_column):
    row = 0
    ordered_nodes: list[str] = []
    ordered_groups = sorted(by_column[column], key=_group_key)
    for index, group in enumerate(ordered_groups):
      if index:
        row += 1
      for node in sorted(group.nodes):
        placements[node] = Placement(column, row)
        ordered_nodes.append(node)
        max_row = max(max_row, row)
        row += 1
    column_nodes[column] = tuple(ordered_nodes)
  return placements, column_nodes, max_row


def _format_columns(
  validated: ValidatedGraph,
  column_nodes: dict[int, tuple[str, ...]],
) -> dict[int, Column]:
  result: dict[int, Column] = {}
  for column in sorted(column_nodes):
    nodes = column_nodes[column]
    entries = tuple(
      FormatEntry(node, validated.node_lane[node].colour)
      for node in nodes
    )
    aligned = validated.graph.formatter(entries)
    if not isinstance(aligned, AlignedColumn):
      raise GraphInputError(
        "column formatter must return AlignedColumn"
      )
    if len(aligned.strings) != len(nodes):
      raise GraphInputError(
        "column formatter must return one string for every node"
      )
    if (
      isinstance(aligned.display_width, bool)
      or not isinstance(aligned.display_width, int)
      or aligned.display_width < 1
    ):
      raise GraphInputError(
        "column formatter returned invalid display width"
      )
    result[column] = Column(
      nodes,
      aligned.strings,
      aligned.display_width,
    )
  return result


def _semantic_edges(
  validated: ValidatedGraph,
) -> tuple[SemanticEdge, ...]:
  result: list[SemanticEdge] = []
  for source in sorted(validated.adjacency):
    for target in sorted(validated.adjacency[source]):
      source_lane = validated.node_lane[source]
      target_lane = validated.node_lane[target]
      lane = source_lane if source_lane is target_lane else None
      colour = (
        lane.colour
        if lane is not None
        else validated.graph.default_edge_colour
      )
      result.append(
        SemanticEdge(
          source=source,
          target=target,
          source_group=validated.node_group[source],
          target_group=validated.node_group[target],
          lane=lane,
          colour=colour,
        )
      )
  return tuple(result)


def _bundle_relations(
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


def _bundle_item_key(
  source: GraphSiblings,
  target: GraphSiblings,
) -> tuple:
  return "bundle", _group_key(source), _group_key(target)


def _boundary_items(
  edges: tuple[SemanticEdge, ...],
  placements: dict[str, Placement],
  ranks: dict[GraphSiblings, int],
  bundle_relations: set[
    tuple[GraphSiblings, GraphSiblings]
  ],
) -> dict[int, tuple[tuple, ...]]:
  values: dict[int, set[tuple]] = {}
  bundled: set[tuple[str, str]] = set()
  for source_group, target_group in bundle_relations:
    boundary = ranks[source_group]
    values.setdefault(boundary, set()).add(
      _bundle_item_key(source_group, target_group)
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
    boundary: tuple(sorted(values.get(boundary, set())))
    for boundary in range(max_column)
  }


def _column_geometry(
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


def _node_tokens(
  column_nodes: dict[int, tuple[str, ...]],
  columns: dict[int, Column],
  placements: dict[str, Placement],
  starts: dict[int, int],
) -> dict[tuple[int, int], NodeToken]:
  result: dict[tuple[int, int], NodeToken] = {}
  for column, nodes in column_nodes.items():
    for node, formatted in zip(
      nodes,
      columns[column].formatted,
    ):
      row = placements[node].row
      result[(starts[column], row)] = NodeToken(
        formatted,
        columns[column].width,
      )
  return result
