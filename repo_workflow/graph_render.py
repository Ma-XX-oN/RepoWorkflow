from __future__ import annotations

from dataclasses import dataclass

from .graph_layout import build_layout
from .graph_render_model import ColourFunction, Graph
from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  GraphLayoutError,
  RouteRecord,
)


@dataclass(frozen=True)
class RenderResult:
  lines: tuple[str, ...]
  routes: tuple[RouteRecord, ...]


def render_graph(graph: Graph) -> RenderResult:
  layout = build_layout(graph)
  if layout.max_y < 0:
    return RenderResult((), ())
  lines = _emit_lines(
    layout.width,
    layout.max_y,
    layout.node_tokens,
    layout.cells,
    layout.default_colour,
  )
  return RenderResult(lines, layout.routes)


def _emit_lines(
  width: int,
  max_y: int,
  node_tokens,
  cells: dict[tuple[int, int], list[Contribution]],
  default_colour: ColourFunction,
) -> tuple[str, ...]:
  lines: list[str] = []
  for y in range(max_y + 1):
    parts: list[str] = []
    x = 0
    while x < width:
      token = node_tokens.get((x, y))
      if token is not None:
        parts.append(token.text)
        x += token.width
        continue
      contributions = cells.get((x, y), [])
      if contributions:
        parts.append(
          _render_cell(contributions, default_colour)
        )
      else:
        parts.append(" ")
      x += 1
    lines.append("".join(parts).rstrip())

  while lines and not lines[-1]:
    lines.pop()
  return tuple(lines)


def _render_cell(
  contributions: list[Contribution],
  default_colour: ColourFunction,
) -> str:
  per_edge: dict[
    tuple[str, str],
    tuple[object, int, tuple[int, int] | None],
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
    lane_edges = [
      edge for edge in edges
      if edge.lane is not None
    ]
    lane_ids = {
      id(edge.lane)
      for edge in lane_edges
    }
    if len(lane_ids) > 1:
      raise GraphLayoutError(
        "shared glyph requires multiple lane colours"
      )
    colour = (
      lane_edges[0].colour
      if lane_edges
      else default_colour
    )
    for _, value, _ in values:
      bits |= value
    return colour(_line_char(bits))

  horizontal = [
    (edge, bits)
    for edge, bits, _ in values
    if bits & (_L | _R)
  ]
  if horizontal:
    edge, bits = sorted(
      horizontal,
      key=lambda item: item[0].key,
    )[0]
    return edge.colour(
      _line_char(bits & (_L | _R))
    )

  edge, bits, _ = sorted(
    values,
    key=lambda item: item[0].key,
  )[0]
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
