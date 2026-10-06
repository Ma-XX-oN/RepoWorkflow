from __future__ import annotations

from dataclasses import dataclass

from .graph_render_model import (
  AlignedColumn,
  ColourFunction,
  FormatEntry,
  Graph,
  GraphInputError,
  GraphSiblings,
  Lane,
  ValidatedGraph,
  validate_graph,
)


_L = 1
_R = 2
_U = 4
_D = 8


class GraphLayoutError(RuntimeError):
  pass


@dataclass(frozen=True)
class HiddenContinuation:
  semantic_source: str
  semantic_target: str
  column: int
  row: int


@dataclass(frozen=True)
class RouteRecord:
  source: str
  target: str
  kind: str
  hidden: tuple[HiddenContinuation, ...]

  def diagnostic(self) -> dict:
    return {
      "source": self.source,
      "target": self.target,
      "kind": self.kind,
      "hidden_columns": [item.column for item in self.hidden],
    }


@dataclass(frozen=True)
class RenderResult:
  lines: tuple[str, ...]
  routes: tuple[RouteRecord, ...]


@dataclass(frozen=True)
class _SemanticEdge:
  source: str
  target: str
  source_group: GraphSiblings
  target_group: GraphSiblings
  lane: Lane | None
  colour: ColourFunction

  @property
  def key(self) -> tuple[str, str]:
    return self.source, self.target


@dataclass(frozen=True)
class _Contribution:
  edge: _SemanticEdge
  bits: int
  bundle: tuple[int, int] | None = None


@dataclass(frozen=True)
class _Placement:
  column: int
  row: int


@dataclass(frozen=True)
class _Column:
  nodes: tuple[str, ...]
  formatted: tuple[str, ...]
  width: int


def render_graph(graph: Graph) -> RenderResult:
  validated = validate_graph(graph)
  if not validated.node_group:
    return RenderResult((), ())

  group_rank = _group_ranks(graph.siblings)
  placements, column_nodes, max_node_row = _place_nodes(
    graph.siblings,
    group_rank,
  )
  columns = _format_columns(
    validated,
    column_nodes,
  )
  edges = _semantic_edges(validated)

  bundle_relations = _bundle_relations(edges, group_rank)
  boundary_items = _boundary_items(
    edges,
    placements,
    group_rank,
    bundle_relations,
  )
  column_start, track_x = _column_geometry(columns, boundary_items)

  cells: dict[tuple[int, int], list[_Contribution]] = {}
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
      _route_adjacent(
        cells,
        edge,
        placements,
        columns,
        column_start,
        x,
        bundle=bundle_id,
      )
      bundled_edges.add(edge.key)
      routes.append(RouteRecord(edge.source, edge.target, "bundle", ()))

  for edge in edges:
    if edge.key in bundled_edges:
      continue
    source = placements[edge.source]
    target = placements[edge.target]
    span = target.column - source.column
    if span <= 0:
      raise GraphLayoutError("semantic edge does not point to a later column")
    if span == 1:
      boundary = source.column
      item_key = _edge_item_key(edge)
      x = track_x[(boundary, item_key)]
      _route_adjacent(
        cells,
        edge,
        placements,
        columns,
        column_start,
        x,
      )
      routes.append(RouteRecord(edge.source, edge.target, "adjacent", ()))
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
    _route_long(
      cells,
      edge,
      placements,
      columns,
      column_start,
      track_x,
      track_y,
    )
    routes.append(RouteRecord(edge.source, edge.target, "long", hidden))

  _validate_routes(validated, placements, tuple(routes))

  max_y = max(
    [max_node_row]
    + [point[1] for point in cells]
    + [
      continuation.row
      for route in routes
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
  lines = _emit_lines(
    width,
    max_y,
    node_tokens,
    cells,
    graph.default_edge_colour,
  )
  return RenderResult(lines, tuple(sorted(routes, key=lambda r: (r.source, r.target))))


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
      ranks[target] = max(ranks.get(target, 0), ranks[group] + 1)
      indegree[target] -= 1
      if indegree[target] == 0:
        ready.append(target)
        ready.sort(key=_group_key)
  if len(seen) != len(groups):
    raise GraphLayoutError("validated graph unexpectedly contains a cycle")
  return ranks


def _place_nodes(
  groups: tuple[GraphSiblings, ...],
  ranks: dict[GraphSiblings, int],
) -> tuple[
  dict[str, _Placement],
  dict[int, tuple[str, ...]],
  int,
]:
  by_column: dict[int, list[GraphSiblings]] = {}
  for group in groups:
    by_column.setdefault(ranks[group], []).append(group)

  placements: dict[str, _Placement] = {}
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
        placements[node] = _Placement(column, row)
        ordered_nodes.append(node)
        max_row = max(max_row, row)
        row += 1
    column_nodes[column] = tuple(ordered_nodes)
  return placements, column_nodes, max_row


def _format_columns(
  validated: ValidatedGraph,
  column_nodes: dict[int, tuple[str, ...]],
) -> dict[int, _Column]:
  result: dict[int, _Column] = {}
  for column in sorted(column_nodes):
    nodes = column_nodes[column]
    entries = tuple(
      FormatEntry(node, validated.node_lane[node].colour)
      for node in nodes
    )
    aligned = validated.graph.formatter(entries)
    if not isinstance(aligned, AlignedColumn):
      raise GraphInputError("column formatter must return AlignedColumn")
    if len(aligned.strings) != len(nodes):
      raise GraphInputError(
        "column formatter must return one string for every node"
      )
    if (
      isinstance(aligned.display_width, bool)
      or not isinstance(aligned.display_width, int)
      or aligned.display_width < 1
    ):
      raise GraphInputError("column formatter returned invalid display width")
    result[column] = _Column(nodes, aligned.strings, aligned.display_width)
  return result


def _semantic_edges(validated: ValidatedGraph) -> tuple[_SemanticEdge, ...]:
  result: list[_SemanticEdge] = []
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
        _SemanticEdge(
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
  edges: tuple[_SemanticEdge, ...],
  ranks: dict[GraphSiblings, int],
) -> set[tuple[GraphSiblings, GraphSiblings]]:
  grouped: dict[
    tuple[GraphSiblings, GraphSiblings],
    list[_SemanticEdge],
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
    lane_ids = {id(edge.lane) for edge in relation_edges if edge.lane is not None}
    if len(lane_ids) <= 1:
      result.add(relation)
  return result


def _bundle_item_key(
  source: GraphSiblings,
  target: GraphSiblings,
) -> tuple:
  return "bundle", _group_key(source), _group_key(target)


def _edge_item_key(edge: _SemanticEdge) -> tuple:
  return "edge", edge.source, edge.target


def _boundary_items(
  edges: tuple[_SemanticEdge, ...],
  placements: dict[str, _Placement],
  ranks: dict[GraphSiblings, int],
  bundle_relations: set[tuple[GraphSiblings, GraphSiblings]],
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
    if target.column == source.column + 1:
      values.setdefault(source.column, set()).add(_edge_item_key(edge))
      continue
    values.setdefault(source.column, set()).add(_edge_item_key(edge))
    values.setdefault(target.column - 1, set()).add(_edge_item_key(edge))

  max_column = max(placement.column for placement in placements.values())
  return {
    boundary: tuple(sorted(values.get(boundary, set())))
    for boundary in range(max_column)
  }


def _column_geometry(
  columns: dict[int, _Column],
  boundary_items: dict[int, tuple[tuple, ...]],
) -> tuple[dict[int, int], dict[tuple[int, tuple], int]]:
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


def _route_adjacent(
  cells: dict[tuple[int, int], list[_Contribution]],
  edge: _SemanticEdge,
  placements: dict[str, _Placement],
  columns: dict[int, _Column],
  starts: dict[int, int],
  track_x: int,
  *,
  bundle: tuple[int, int] | None = None,
) -> None:
  source = placements[edge.source]
  target = placements[edge.target]
  source_x = starts[source.column] + columns[source.column].width
  target_x = starts[target.column] - 1
  _horizontal(cells, edge, source_x, track_x, source.row, bundle)
  _vertical(cells, edge, track_x, source.row, target.row, bundle)
  _horizontal(cells, edge, track_x, target_x, target.row, bundle)


def _route_long(
  cells: dict[tuple[int, int], list[_Contribution]],
  edge: _SemanticEdge,
  placements: dict[str, _Placement],
  columns: dict[int, _Column],
  starts: dict[int, int],
  tracks: dict[tuple[int, tuple], int],
  track_y: int,
) -> None:
  source = placements[edge.source]
  target = placements[edge.target]
  item = _edge_item_key(edge)
  source_track = tracks[(source.column, item)]
  target_track = tracks[(target.column - 1, item)]
  source_x = starts[source.column] + columns[source.column].width
  target_x = starts[target.column] - 1
  _horizontal(cells, edge, source_x, source_track, source.row, None)
  _vertical(cells, edge, source_track, source.row, track_y, None)
  _horizontal(cells, edge, source_track, target_track, track_y, None)
  _vertical(cells, edge, target_track, track_y, target.row, None)
  _horizontal(cells, edge, target_track, target_x, target.row, None)


def _add(
  cells: dict[tuple[int, int], list[_Contribution]],
  point: tuple[int, int],
  edge: _SemanticEdge,
  bits: int,
  bundle: tuple[int, int] | None,
) -> None:
  cells.setdefault(point, []).append(_Contribution(edge, bits, bundle))


def _horizontal(
  cells: dict[tuple[int, int], list[_Contribution]],
  edge: _SemanticEdge,
  x1: int,
  x2: int,
  y: int,
  bundle: tuple[int, int] | None,
) -> None:
  if x2 < x1:
    x1, x2 = x2, x1
  for x in range(x1, x2 + 1):
    bits = 0
    if x > x1:
      bits |= _L
    if x < x2:
      bits |= _R
    if bits:
      _add(cells, (x, y), edge, bits, bundle)


def _vertical(
  cells: dict[tuple[int, int], list[_Contribution]],
  edge: _SemanticEdge,
  x: int,
  y1: int,
  y2: int,
  bundle: tuple[int, int] | None,
) -> None:
  if y2 < y1:
    y1, y2 = y2, y1
  for y in range(y1, y2 + 1):
    bits = 0
    if y > y1:
      bits |= _U
    if y < y2:
      bits |= _D
    if bits:
      _add(cells, (x, y), edge, bits, bundle)


def _node_tokens(
  column_nodes: dict[int, tuple[str, ...]],
  columns: dict[int, _Column],
  placements: dict[str, _Placement],
  starts: dict[int, int],
) -> dict[tuple[int, int], tuple[str, int]]:
  result: dict[tuple[int, int], tuple[str, int]] = {}
  for column, nodes in column_nodes.items():
    for node, formatted in zip(nodes, columns[column].formatted):
      row = placements[node].row
      result[(starts[column], row)] = (formatted, columns[column].width)
  return result


def _emit_lines(
  width: int,
  max_y: int,
  node_tokens: dict[tuple[int, int], tuple[str, int]],
  cells: dict[tuple[int, int], list[_Contribution]],
  default_colour: ColourFunction,
) -> tuple[str, ...]:
  lines: list[str] = []
  for y in range(max_y + 1):
    parts: list[str] = []
    x = 0
    while x < width:
      token = node_tokens.get((x, y))
      if token is not None:
        text, token_width = token
        parts.append(text)
        x += token_width
        continue
      contributions = cells.get((x, y), [])
      if contributions:
        parts.append(_render_cell(contributions, default_colour))
      else:
        parts.append(" ")
      x += 1
    lines.append("".join(parts).rstrip())

  while lines and not lines[-1]:
    lines.pop()
  return tuple(lines)


def _render_cell(
  contributions: list[_Contribution],
  default_colour: ColourFunction,
) -> str:
  per_edge: dict[tuple[str, str], tuple[_SemanticEdge, int, tuple[int, int] | None]] = {}
  for item in contributions:
    key = item.edge.key
    previous = per_edge.get(key)
    if previous is None:
      per_edge[key] = item.edge, item.bits, item.bundle
    else:
      edge, bits, bundle = previous
      per_edge[key] = edge, bits | item.bits, bundle

  values = list(per_edge.values())
  if len(values) == 1:
    edge, bits, _ = values[0]
    return edge.colour(_line_char(bits))

  edges = [value[0] for value in values]
  bundles = {value[2] for value in values}
  same_source = len({edge.source for edge in edges}) == 1
  same_target = len({edge.target for edge in edges}) == 1
  same_bundle = len(bundles) == 1 and None not in bundles
  if same_source or same_target or same_bundle:
    bits = 0
    lane_edges = [edge for edge in edges if edge.lane is not None]
    lane_ids = {id(edge.lane) for edge in lane_edges}
    if len(lane_ids) > 1:
      raise GraphLayoutError("shared glyph requires multiple lane colours")
    colour = lane_edges[0].colour if lane_edges else default_colour
    for _, value, _ in values:
      bits |= value
    return colour(_line_char(bits))

  horizontal = [
    (edge, bits)
    for edge, bits, _ in values
    if bits & (_L | _R)
  ]
  if horizontal:
    edge, bits = sorted(horizontal, key=lambda item: item[0].key)[0]
    return edge.colour(_line_char(bits & (_L | _R)))

  edge, bits, _ = sorted(values, key=lambda item: item[0].key)[0]
  return edge.colour(_line_char(bits))


def _line_char(bits: int) -> str:
  mapping = {
    _L: "─",
    _R: "─",
    _L | _R: "─",
    _U: "│",
    _D: "│",
    _U | _D: "│",
    _R | _D: "┌",
    _L | _D: "┐",
    _R | _U: "└",
    _L | _U: "┘",
    _R | _U | _D: "├",
    _L | _U | _D: "┤",
    _L | _R | _D: "┬",
    _L | _R | _U: "┴",
    _L | _R | _U | _D: "┼",
  }
  return mapping.get(bits, "─")


def _validate_routes(
  validated: ValidatedGraph,
  placements: dict[str, _Placement],
  routes: tuple[RouteRecord, ...],
) -> None:
  expected = {
    (source, target)
    for source, targets in validated.adjacency.items()
    for target in targets
  }
  actual = {(route.source, route.target) for route in routes}
  if actual != expected or len(routes) != len(expected):
    raise GraphLayoutError("logical routes do not match semantic relationships")

  for route in routes:
    source_column = placements[route.source].column
    target_column = placements[route.target].column
    expected_columns = tuple(range(source_column + 1, target_column))
    actual_columns = tuple(item.column for item in route.hidden)
    if actual_columns != expected_columns:
      raise GraphLayoutError("hidden continuation columns are incomplete")
    for item in route.hidden:
      if (
        item.semantic_source != route.source
        or item.semantic_target != route.target
      ):
        raise GraphLayoutError("hidden continuation lost semantic endpoints")
