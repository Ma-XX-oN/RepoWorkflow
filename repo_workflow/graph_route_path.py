from __future__ import annotations

from .graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  GraphLayoutError,
)


def collect_routed_edge_bits(
  cells: dict[tuple[int, int], list[Contribution]],
) -> dict[
  tuple[str, str],
  dict[tuple[int, int], int],
]:
  result: dict[
    tuple[str, str],
    dict[tuple[int, int], int],
  ] = {}
  for point, contributions in cells.items():
    for contribution in contributions:
      route = result.setdefault(contribution.edge.key, {})
      route[point] = route.get(point, 0) | contribution.bits
  return result


def simple_path(
  route_bits: dict[tuple[int, int], int],
  source: tuple[int, int],
  target: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
  directions = (
    (_L, (-1, 0), _R),
    (_R, (1, 0), _L),
    (_U, (0, -1), _D),
    (_D, (0, 1), _U),
  )
  neighbours: dict[
    tuple[int, int],
    list[tuple[int, int]],
  ] = {}

  for point, bits in route_bits.items():
    x, y = point
    values: list[tuple[int, int]] = []
    for bit, (dx, dy), reciprocal in directions:
      if not bits & bit:
        continue
      neighbour = (x + dx, y + dy)
      neighbour_bits = route_bits.get(neighbour, 0)
      if not neighbour_bits & reciprocal:
        raise GraphLayoutError(
          "semantic edge route contains a dangling or one-way segment; "
          f"point={point!r}; neighbour={neighbour!r}; bit={bit!r}"
        )
      values.append(neighbour)
    neighbours[point] = values

  branching = {
    point: tuple(values)
    for point, values in neighbours.items()
    if len(values) > 2
  }
  if branching:
    raise GraphLayoutError(
      "one semantic edge route branches or self-intersects; "
      f"source={source!r}; target={target!r}; branching={branching!r}"
    )

  if source not in neighbours or target not in neighbours:
    raise GraphLayoutError(
      "semantic edge route is missing an endpoint anchor"
    )

  path = [source]
  previous = None
  current = source
  while current != target:
    choices = [
      point
      for point in neighbours[current]
      if point != previous
    ]
    if len(choices) != 1:
      raise GraphLayoutError(
        "semantic edge route is not one simple path"
      )
    previous, current = current, choices[0]
    path.append(current)
    if len(path) > len(route_bits):
      raise GraphLayoutError("semantic edge route contains a loop")

  if len(path) != len(route_bits):
    raise GraphLayoutError(
      "semantic edge route contains geometry outside its endpoint path"
    )
  return tuple(path)
