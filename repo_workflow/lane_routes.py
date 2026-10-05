from __future__ import annotations

from dataclasses import dataclass

from .lane_selection import LaneSelection


_L = 1
_R = 2
_U = 4
_D = 8


@dataclass(frozen=True)
class EdgeRoute:
  source: str
  target: str
  kind: str
  track_y: int | None
  cells: dict[tuple[int, int], int]

  def diagnostic(self) -> dict:
    value = {
      "source": int(self.source),
      "target": int(self.target),
      "kind": self.kind,
    }
    if self.track_y is not None:
      value["track_y"] = self.track_y
    return value


@dataclass(frozen=True)
class RoutePlan:
  positions: dict[str, tuple[int, int]]
  routes: tuple[EdgeRoute, ...]
  cells: dict[tuple[int, int], dict[tuple[str, str], int]]
  max_y: int


def plan_routes(
  selection: LaneSelection,
  dependencies: dict[str, tuple[str, ...]],
  depths: dict[str, int],
  column_start: dict[int, int],
  column_width: dict[int, int],
  labels: dict[str, str],
) -> RoutePlan:
  positions, primary = _place_nodes(selection, dependencies, depths)
  routes: list[EdgeRoute] = []

  node_max_y = max((y for _, y in positions.values()), default=0)
  bypass_index = 0
  edges = [
    (source, target)
    for target in sorted(dependencies, key=int)
    for source in sorted(dependencies[target], key=int)
  ]

  for source, target in edges:
    if (source, target) in primary:
      routes.append(_primary_route(
        source,
        target,
        positions,
        column_start,
        labels,
      ))
      continue

    track_y = node_max_y + 2 + bypass_index * 2
    bypass_index += 1
    routes.append(_bypass_route(
      source,
      target,
      track_y,
      positions,
      column_start,
      column_width,
      labels,
    ))

  cells: dict[tuple[int, int], dict[tuple[str, str], int]] = {}
  for route in routes:
    edge = (route.source, route.target)
    for point, bits in route.cells.items():
      cells.setdefault(point, {})[edge] = bits

  max_y = max(
    [node_max_y]
    + [y for x, y in cells]
  )
  return RoutePlan(
    positions=positions,
    routes=tuple(routes),
    cells=cells,
    max_y=max_y,
  )


def render_route_cell(edges: dict[tuple[str, str], int]) -> str:
  if not edges:
    return " "
  if len(edges) == 1:
    return _line_char(next(iter(edges.values())))

  identities = tuple(edges)
  same_source = len({source for source, _ in identities}) == 1
  same_target = len({target for _, target in identities}) == 1
  if same_source or same_target:
    bits = 0
    for value in edges.values():
      bits |= value
    return _line_char(bits)

  # Unrelated routes crossing the same screen cell are deliberately rendered
  # as a crossing, never as a dependency junction.
  return "╳"


def _place_nodes(
  selection: LaneSelection,
  dependencies: dict[str, tuple[str, ...]],
  depths: dict[str, int],
) -> tuple[dict[str, tuple[int, int]], set[tuple[str, str]]]:
  positions: dict[str, tuple[int, int]] = {}
  occupied: dict[int, set[int]] = {}
  primary: set[tuple[str, str]] = set()
  used_primary_sources: set[str] = set()

  for issue in sorted(dependencies, key=lambda value: (depths[value], int(value))):
    column = depths[issue]
    used = occupied.setdefault(column, set())
    candidates = [
      source
      for source in dependencies[issue]
      if depths[source] + 1 == column
    ]
    candidates.sort(key=lambda source: (
      selection.assignment[source] != selection.assignment[issue],
      source in used_primary_sources,
      int(source),
    ))

    parent = next(
      (
        source
        for source in candidates
        if source not in used_primary_sources
        and positions[source][1] not in used
      ),
      None,
    )
    if parent is not None:
      y = positions[parent][1]
      primary.add((parent, issue))
      used_primary_sources.add(parent)
    else:
      y = _next_node_row(used)

    used.add(y)
    positions[issue] = (column, y)

  return positions, primary


def _next_node_row(used: set[int]) -> int:
  y = 0
  while y in used:
    y += 2
  return y


def _primary_route(
  source: str,
  target: str,
  positions: dict[str, tuple[int, int]],
  column_start: dict[int, int],
  labels: dict[str, str],
) -> EdgeRoute:
  source_column, source_y = positions[source]
  target_column, target_y = positions[target]
  if target_column != source_column + 1 or target_y != source_y:
    raise ValueError("primary lane route must be straight and adjacent")

  cells: dict[tuple[int, int], int] = {}
  start = column_start[source_column] + len(labels[source]) + 1
  end = column_start[target_column] - 1
  _horizontal(cells, start, end, source_y)
  return EdgeRoute(source, target, "primary", None, cells)


def _bypass_route(
  source: str,
  target: str,
  track_y: int,
  positions: dict[str, tuple[int, int]],
  column_start: dict[int, int],
  column_width: dict[int, int],
  labels: dict[str, str],
) -> EdgeRoute:
  source_column, source_y = positions[source]
  target_column, target_y = positions[target]
  source_port = column_start[source_column] + column_width[source_column] + 2
  target_port = column_start[target_column] - 2
  cells: dict[tuple[int, int], int] = {}

  label_end = column_start[source_column] + len(labels[source])
  _horizontal(cells, label_end + 1, source_port, source_y)
  _vertical(cells, source_port, source_y, track_y)
  _horizontal(cells, source_port, target_port, track_y)
  _vertical(cells, target_port, track_y, target_y)
  _horizontal(cells, target_port, column_start[target_column] - 1, target_y)

  return EdgeRoute(
    source,
    target,
    f"bypass[{track_y}]",
    track_y,
    cells,
  )


def _horizontal(
  cells: dict[tuple[int, int], int],
  x1: int,
  x2: int,
  y: int,
) -> None:
  if x2 < x1:
    x1, x2 = x2, x1
  if x1 == x2:
    cells[(x1, y)] = cells.get((x1, y), 0) | _L | _R
    return
  for x in range(x1, x2 + 1):
    bits = 0
    if x > x1:
      bits |= _L
    if x < x2:
      bits |= _R
    cells[(x, y)] = cells.get((x, y), 0) | bits


def _vertical(
  cells: dict[tuple[int, int], int],
  x: int,
  y1: int,
  y2: int,
) -> None:
  if y2 < y1:
    y1, y2 = y2, y1
  if y1 == y2:
    cells[(x, y1)] = cells.get((x, y1), 0) | _U | _D
    return
  for y in range(y1, y2 + 1):
    bits = 0
    if y > y1:
      bits |= _U
    if y < y2:
      bits |= _D
    cells[(x, y)] = cells.get((x, y), 0) | bits


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
