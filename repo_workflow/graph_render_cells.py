from __future__ import annotations

from dataclasses import dataclass

from .graph_render_model import ColourFunction, GraphSiblings, Lane


_L = 1
_R = 2
_U = 4
_D = 8


class GraphCellError(RuntimeError):
  pass


@dataclass(frozen=True)
class SemanticEdge:
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
class Contribution:
  edge: SemanticEdge
  bits: int
  bundle: tuple[int, int] | None = None


def horizontal(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
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


def vertical(
  cells: dict[tuple[int, int], list[Contribution]],
  edge: SemanticEdge,
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


def render_cell(
  contributions: list[Contribution],
  default_colour: ColourFunction,
) -> str:
  per_edge: dict[
    tuple[str, str],
    tuple[SemanticEdge, int, tuple[int, int] | None],
  ] = {}
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
      raise GraphCellError("shared glyph requires multiple lane colours")
    colour = lane_edges[0].colour if lane_edges else default_colour
    for _, value, _ in values:
      bits |= value
    return colour(_line_char(bits))

  horizontal_values = [
    (edge, bits)
    for edge, bits, _ in values
    if bits & (_L | _R)
  ]
  if horizontal_values:
    edge, bits = sorted(horizontal_values, key=lambda item: item[0].key)[0]
    return edge.colour(_line_char(bits & (_L | _R)))

  edge, bits, _ = sorted(values, key=lambda item: item[0].key)[0]
  return edge.colour(_line_char(bits))


def _add(
  cells: dict[tuple[int, int], list[Contribution]],
  point: tuple[int, int],
  edge: SemanticEdge,
  bits: int,
  bundle: tuple[int, int] | None,
) -> None:
  cells.setdefault(point, []).append(Contribution(edge, bits, bundle))


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
