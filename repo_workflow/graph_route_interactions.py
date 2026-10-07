from __future__ import annotations

from .graph_render_types import Contribution, SemanticEdge


def interaction_component(
  cells: dict[tuple[int, int], list[Contribution]],
  start: tuple[str, str],
) -> set[tuple[str, str]]:
  adjacency: dict[
    tuple[str, str],
    set[tuple[str, str]],
  ] = {}
  for contributions in cells.values():
    switch_edges = switch_edges_for_cell(tuple(contributions))
    if not switch_edges:
      continue
    for edge in switch_edges:
      adjacency.setdefault(edge, set()).update(
        switch_edges - {edge}
      )

  pending = [start]
  seen: set[tuple[str, str]] = set()
  while pending:
    edge = pending.pop()
    if edge in seen:
      continue
    seen.add(edge)
    pending.extend(adjacency.get(edge, set()) - seen)
  return seen


def switch_edges_for_cell(
  contributions: tuple[Contribution, ...],
) -> set[tuple[str, str]]:
  edge_map: dict[
    tuple[str, str],
    tuple[SemanticEdge, int, tuple[int, int] | None],
  ] = {}
  for contribution in contributions:
    key = contribution.edge.key
    previous = edge_map.get(key)
    if previous is None:
      edge_map[key] = (
        contribution.edge,
        contribution.bits,
        contribution.bundle,
      )
    else:
      edge, bits, bundle = previous
      edge_map[key] = (
        edge,
        bits | contribution.bits,
        bundle,
      )

  if len(edge_map) < 2:
    return set()

  values = list(edge_map.values())
  same_source = len({
    edge.source
    for edge, _, _ in values
  }) == 1
  same_target = len({
    edge.target
    for edge, _, _ in values
  }) == 1
  bundles = {
    bundle
    for _, _, bundle in values
  }
  same_bundle = len(bundles) == 1 and None not in bundles
  shared_bits = values[0][1]
  for _, bits, _ in values[1:]:
    shared_bits &= bits
  shared_endpoint = (same_source or same_target) and bool(shared_bits)

  if shared_endpoint or same_bundle:
    return set(edge_map)
  return set()
