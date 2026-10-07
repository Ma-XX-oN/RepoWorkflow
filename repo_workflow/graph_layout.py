from __future__ import annotations

from .graph_geometry import (
  edge_item_key,
  route_adjacent,
  route_candidate_preserves_reachability,
  route_long,
  validate_routes,
)
from .graph_long_routes import choose_long_route_row
from .graph_ordering import group_key, group_ranks, place_nodes
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
  _D,
  _L,
  _R,
  _U,
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

  group_rank = group_ranks(graph.siblings)
  placements, column_nodes, max_node_row = place_nodes(
    validated,
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
  used_long_rows: dict[int, list[SemanticEdge]] = {}
  bundled_edges: set[tuple[str, str]] = set()

  for relation in sorted(
    bundle_relations,
    key=lambda item: (
      group_key(item[0]),
      group_key(item[1]),
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

    track_y = choose_long_route_row(
      edge,
      placements,
      max_node_row,
      used_long_rows,
      lambda row: _long_route_crossings(
        edge,
        row,
        cells,
        placements,
        columns,
        column_start,
        track_x,
      ),
      lambda row: _long_route_candidate_valid(
        edge,
        row,
        cells,
        routes,
        validated,
        placements,
        columns,
        column_start,
        track_x,
      ),
    )
    used_long_rows.setdefault(track_y, []).append(edge)
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
  validate_routes(
    validated,
    placements,
    columns,
    column_start,
    cells,
    ordered_routes,
  )

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


def _long_route_candidate_valid(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  routes: list[RouteRecord],
  validated: ValidatedGraph,
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
) -> bool:
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
  )
  expected = {
    (route.source, route.target)
    for route in routes
  }
  expected.add(edge.key)
  return route_candidate_preserves_reachability(
    validated,
    placements,
    columns,
    starts,
    candidate_cells,
    expected,
  )


def _long_route_crossings(
  edge: SemanticEdge,
  row: int,
  cells: dict[tuple[int, int], list[Contribution]],
  placements: dict[str, Placement],
  columns: dict[int, Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
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
  return "bundle", group_key(source), group_key(target)


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
    boundary: tuple(
      sorted(
        values.get(boundary, set()),
        key=lambda item: _boundary_item_order(
          item,
          placements,
        ),
      )
    )
    for boundary in range(max_column)
  }


def _boundary_item_order(
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
