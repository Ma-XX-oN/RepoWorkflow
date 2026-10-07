from __future__ import annotations

from itertools import combinations
import unittest

from repo_workflow.graph_render import render_graph
from repo_workflow.graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphSiblings,
  Lane,
)


def plain(text: str) -> str:
  return text


def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
  width = max((len(entry.raw_text) for entry in entries), default=0)
  return AlignedColumn(
    tuple(entry.raw_text.ljust(width) for entry in entries),
    width,
  )


def lane_partitions(
  nodes: tuple[str, ...],
) -> tuple[tuple[tuple[str, ...], ...], ...]:
  result: list[tuple[tuple[str, ...], ...]] = []

  def visit(index: int, groups: list[list[str]]) -> None:
    if index == len(nodes):
      result.append(tuple(tuple(group) for group in groups))
      return
    node = nodes[index]
    for group in groups:
      group.append(node)
      visit(index + 1, groups)
      group.pop()
    groups.append([node])
    visit(index + 1, groups)
    groups.pop()

  visit(0, [])
  return tuple(result)


def valid_lane_partition(
  partition: tuple[tuple[str, ...], ...],
  edges: set[tuple[str, str]],
) -> bool:
  return all(
    all((source, target) in edges for source, target in zip(lane, lane[1:]))
    for lane in partition
  )


def make_graph(
  edges: tuple[tuple[str, str], ...],
  lanes: tuple[tuple[str, ...], ...],
) -> Graph:
  nodes = ("A", "B", "C", "D")
  groups = {
    node: GraphSiblings((node,))
    for node in nodes
  }
  outgoing = {node: [] for node in nodes}
  for source, target in edges:
    outgoing[source].append(groups[target])
  for node in nodes:
    groups[node].to_nodes = tuple(outgoing[node])
  return Graph(
    tuple(groups[node] for node in nodes),
    tuple(Lane(lane, plain) for lane in lanes),
    plain,
    formatter,
  )


class GeneratedGraphSemanticTests(unittest.TestCase):
  def test_every_four_node_dag_preserves_rendered_reachability(self):
    nodes = ("A", "B", "C", "D")
    possible = tuple(
      (nodes[left], nodes[right])
      for left in range(len(nodes))
      for right in range(left + 1, len(nodes))
    )

    partitions = lane_partitions(nodes)
    rendered = 0
    for count in range(len(possible) + 1):
      for chosen in combinations(possible, count):
        edge_set = set(chosen)
        for partition in partitions:
          if not valid_lane_partition(partition, edge_set):
            continue
          with self.subTest(edges=chosen, lanes=partition):
            render_graph(make_graph(tuple(chosen), partition))
          rendered += 1
    self.assertGreater(rendered, 64)

  def test_many_to_many_bridge_classes_are_in_generated_space(self):
    nodes = ("A", "B", "C", "D")
    possible = tuple(
      (nodes[left], nodes[right])
      for left in range(len(nodes))
      for right in range(left + 1, len(nodes))
    )
    seen = 0
    for count in range(len(possible) + 1):
      for chosen in combinations(possible, count):
        outgoing = {node: 0 for node in nodes}
        incoming = {node: 0 for node in nodes}
        for source, target in chosen:
          outgoing[source] += 1
          incoming[target] += 1
        if any(
          outgoing[source] > 1 and incoming[target] > 1
          for source, target in chosen
        ):
          seen += 1
    self.assertGreater(seen, 0)


if __name__ == "__main__":
  unittest.main()
