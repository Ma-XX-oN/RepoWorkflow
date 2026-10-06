from __future__ import annotations

from itertools import combinations
import unittest

from repo_workflow.graph_layout import build_layout
from repo_workflow.graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphSiblings,
  Lane,
)


def colour(text: str) -> str:
  return text


def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
  width = max((len(entry.raw_text) for entry in entries), default=0)
  return AlignedColumn(
    tuple(entry.raw_text.ljust(width) for entry in entries),
    width,
  )


def node_positions(layout):
  result = {}
  for (x, y), token in layout.node_tokens.items():
    result[token.text.rstrip()] = (x, y, token.width)
  return result


def edge_cells(layout):
  result = {}
  for point, contributions in layout.cells.items():
    for item in contributions:
      result.setdefault(item.edge.key, set()).add(point)
  return result


def assert_connected(test, points):
  pending = {next(iter(points))}
  visited = set()
  while pending:
    point = pending.pop()
    if point in visited:
      continue
    visited.add(point)
    x, y = point
    for neighbour in (
      (x - 1, y),
      (x + 1, y),
      (x, y - 1),
      (x, y + 1),
    ):
      if neighbour in points and neighbour not in visited:
        pending.add(neighbour)
  test.assertEqual(visited, points)


class GraphLayoutSemanticTests(unittest.TestCase):
  def assert_semantic_geometry(self, graph, expected):
    layout = build_layout(graph)
    positions = node_positions(layout)
    routed = edge_cells(layout)

    self.assertEqual(set(routed), expected)
    for source, target in expected:
      points = routed[(source, target)]
      self.assertTrue(points)
      source_x, source_y, source_width = positions[source]
      target_x, target_y, _ = positions[target]
      self.assertIn((source_x + source_width, source_y), points)
      self.assertIn((target_x - 1, target_y), points)
      assert_connected(self, points)

  def test_multi_overlap_geometry_preserves_exact_edge_set(self):
    x = GraphSiblings(("X",))
    y = GraphSiblings(("Y",))
    z = GraphSiblings(("Z",))
    a = GraphSiblings(("A",), (x,))
    b = GraphSiblings(("B",), (x, y, z))
    c = GraphSiblings(("C",), (y,))
    d = GraphSiblings(("D",), (z,))
    graph = Graph(
      (a, b, c, d, x, y, z),
      (
        Lane(("A", "X"), colour),
        Lane(("B", "Z"), colour),
        Lane(("C", "Y"), colour),
        Lane(("D",), colour),
      ),
      colour,
      formatter,
    )
    self.assert_semantic_geometry(
      graph,
      {
        ("A", "X"),
        ("B", "X"),
        ("B", "Y"),
        ("B", "Z"),
        ("C", "Y"),
        ("D", "Z"),
      },
    )

  def test_long_edge_variants_preserve_connected_routes(self):
    optional = (("A", "C"), ("A", "D"), ("B", "D"))
    for count in range(len(optional) + 1):
      for chosen in combinations(optional, count):
        with self.subTest(chosen=chosen):
          d = GraphSiblings(("D",))
          c_targets = (d,)
          c = GraphSiblings(("C",), c_targets)
          b_targets = [c]
          if ("B", "D") in chosen:
            b_targets.append(d)
          b = GraphSiblings(("B",), tuple(b_targets))
          a_targets = [b]
          if ("A", "C") in chosen:
            a_targets.append(c)
          if ("A", "D") in chosen:
            a_targets.append(d)
          a = GraphSiblings(("A",), tuple(a_targets))
          graph = Graph(
            (a, b, c, d),
            (Lane(("A", "B", "C", "D"), colour),),
            colour,
            formatter,
          )
          expected = {
            ("A", "B"),
            ("B", "C"),
            ("C", "D"),
            *chosen,
          }
          self.assert_semantic_geometry(graph, expected)


if __name__ == "__main__":
  unittest.main()
