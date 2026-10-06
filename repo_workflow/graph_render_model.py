from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


ColourFunction = Callable[[str], str]


@dataclass(eq=False)
class GraphSiblings:
  nodes: tuple[str, ...]
  to_nodes: tuple["GraphSiblings", ...] = ()


@dataclass(frozen=True)
class Lane:
  nodes: tuple[str, ...]
  colour: ColourFunction


@dataclass(frozen=True)
class FormatEntry:
  raw_text: str
  colour: ColourFunction


@dataclass(frozen=True)
class AlignedColumn:
  strings: tuple[str, ...]
  display_width: int


ColumnFormatter = Callable[[tuple[FormatEntry, ...]], AlignedColumn]


@dataclass(frozen=True)
class Graph:
  siblings: tuple[GraphSiblings, ...]
  lanes: tuple[Lane, ...]
  default_edge_colour: ColourFunction
  formatter: ColumnFormatter


class GraphInputError(ValueError):
  pass


@dataclass(frozen=True)
class ValidatedGraph:
  graph: Graph
  node_group: dict[str, GraphSiblings]
  node_lane: dict[str, Lane]
  adjacency: dict[str, frozenset[str]]
  incoming: dict[str, frozenset[str]]


def validate_graph(graph: Graph) -> ValidatedGraph:
  if not callable(graph.default_edge_colour):
    raise GraphInputError("default edge colour must be callable")
  if not callable(graph.formatter):
    raise GraphInputError("column formatter must be callable")

  group_ids = {id(group) for group in graph.siblings}
  if len(group_ids) != len(graph.siblings):
    raise GraphInputError("GraphSiblings objects must be unique")

  node_group: dict[str, GraphSiblings] = {}
  adjacency_mutable: dict[str, set[str]] = {}
  incoming_mutable: dict[str, set[str]] = {}

  for group in graph.siblings:
    if not group.nodes:
      raise GraphInputError("GraphSiblings nodes must not be empty")
    if len(set(group.nodes)) != len(group.nodes):
      raise GraphInputError("duplicate node text in GraphSiblings")
    for node in group.nodes:
      if not isinstance(node, str) or not node:
        raise GraphInputError("node text must be non-empty text")
      if node in node_group:
        raise GraphInputError(f"duplicate node text: {node!r}")
      node_group[node] = group
      adjacency_mutable[node] = set()
      incoming_mutable[node] = set()

  for group in graph.siblings:
    target_ids = [id(target) for target in group.to_nodes]
    if len(set(target_ids)) != len(target_ids):
      raise GraphInputError("duplicate GraphSiblings relationship")
    for target in group.to_nodes:
      if id(target) not in group_ids:
        raise GraphInputError("GraphSiblings target is outside the graph")
      if target is group:
        raise GraphInputError("GraphSiblings graph must be acyclic")
      for source_node in group.nodes:
        for target_node in target.nodes:
          if target_node in adjacency_mutable[source_node]:
            raise GraphInputError("duplicate semantic relationship")
          adjacency_mutable[source_node].add(target_node)
          incoming_mutable[target_node].add(source_node)

  _validate_acyclic(graph.siblings)

  node_lane: dict[str, Lane] = {}
  for lane in graph.lanes:
    if not lane.nodes:
      raise GraphInputError("lane nodes must not be empty")
    if not callable(lane.colour):
      raise GraphInputError("lane colour must be callable")
    if len(set(lane.nodes)) != len(lane.nodes):
      raise GraphInputError("duplicate node in lane")
    for node in lane.nodes:
      if node not in node_group:
        raise GraphInputError(f"lane references unknown node: {node!r}")
      if node in node_lane:
        raise GraphInputError(f"node belongs to multiple lanes: {node!r}")
      node_lane[node] = lane
    for source, target in zip(lane.nodes, lane.nodes[1:]):
      if target not in adjacency_mutable[source]:
        raise GraphInputError(
          f"lane is not a directed path: {source!r} -> {target!r}"
        )

  missing = set(node_group) - set(node_lane)
  if missing:
    raise GraphInputError(
      "every visible node must belong to exactly one lane: "
      + ", ".join(sorted(repr(node) for node in missing))
    )

  adjacency = {
    node: frozenset(targets)
    for node, targets in adjacency_mutable.items()
  }
  incoming = {
    node: frozenset(sources)
    for node, sources in incoming_mutable.items()
  }
  return ValidatedGraph(graph, node_group, node_lane, adjacency, incoming)


def _validate_acyclic(groups: tuple[GraphSiblings, ...]) -> None:
  state: dict[int, int] = {}

  def visit(group: GraphSiblings) -> None:
    key = id(group)
    current = state.get(key, 0)
    if current == 1:
      raise GraphInputError("GraphSiblings graph must be acyclic")
    if current == 2:
      return
    state[key] = 1
    for target in group.to_nodes:
      visit(target)
    state[key] = 2

  for group in groups:
    visit(group)
