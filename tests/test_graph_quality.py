from __future__ import annotations

import unittest

from repo_workflow.graph_layout import build_layout
from repo_workflow.graph_quality import measure_layout
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


def make_graph(nodes, edges, lanes):
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
    tuple(
      Lane(tuple(lane), colour)
      for lane in lanes
    ),
    colour,
    formatter,
  )


class GraphQualityTests(unittest.TestCase):
  def test_long_edge_avoids_needless_below_graph_dip(self):
    graph = make_graph(
      ("A", "B", "C", "X", "P"),
      (
        ("A", "X"),
        ("C", "X"),
        ("X", "P"),
        ("B", "P"),
      ),
      (
        ("A", "X", "P"),
        ("B",),
        ("C",),
      ),
    )
    layout = build_layout(graph)
    positions = {
      token.text.strip(): y
      for (_, y), token in layout.node_tokens.items()
    }
    route = next(
      item
      for item in layout.routes
      if (item.source, item.target) == ("B", "P")
    )
    self.assertTrue(route.hidden)
    low = min(positions["B"], positions["P"])
    high = max(positions["B"], positions["P"])
    self.assertTrue(
      all(low <= item.row <= high for item in route.hidden)
    )
    self.assertLessEqual(layout.max_y, high)

  def test_multi_overlap_avoids_adjacent_opposing_verticals(self):
    graph = make_graph(
      ("A", "B", "C", "D", "X", "Y", "Z"),
      (
        ("A", "X"),
        ("B", "X"),
        ("B", "Y"),
        ("C", "Y"),
        ("B", "Z"),
        ("D", "Z"),
      ),
      (
        ("A", "X"),
        ("B", "Z"),
        ("C", "Y"),
        ("D",),
      ),
    )
    quality = measure_layout(build_layout(graph))
    self.assertEqual(quality.opposing_adjacent_verticals, 0)

  def test_real_107_shape_remains_compact(self):
    graph = make_graph(
      ("89", "118", "105", "106", "107"),
      (
        ("89", "118"),
        ("118", "105"),
        ("118", "106"),
        ("105", "107"),
        ("106", "107"),
      ),
      (
        ("89", "118", "105", "107"),
        ("106",),
      ),
    )
    layout = build_layout(graph)
    self.assertLessEqual(layout.max_y, 2)
    self.assertEqual(
      {(route.source, route.target) for route in layout.routes},
      {
        ("89", "118"),
        ("118", "105"),
        ("118", "106"),
        ("105", "107"),
        ("106", "107"),
      },
    )

  def test_real_218_shape_improves_legacy_long_edge_excursion(self):
    nodes = (
      "77", "78", "99", "100", "101", "127", "145",
      "185", "186", "189", "208", "216", "217", "218",
    )
    edges = (
      ("77", "78"),
      ("77", "145"),
      ("77", "185"),
      ("78", "99"),
      ("99", "100"),
      ("99", "101"),
      ("99", "189"),
      ("100", "101"),
      ("101", "145"),
      ("127", "77"),
      ("145", "185"),
      ("145", "216"),
      ("185", "216"),
      ("186", "185"),
      ("189", "186"),
      ("208", "216"),
      ("216", "217"),
      ("217", "218"),
    )
    graph = make_graph(
      nodes,
      edges,
      (
        (
          "127", "77", "78", "99", "100", "101",
          "145", "185", "216", "217", "218",
        ),
        ("189", "186"),
        ("208",),
      ),
    )
    layout = build_layout(graph)
    visible_max = max(y for (_, y) in layout.node_tokens)
    long_routes = [
      route for route in layout.routes if route.hidden
    ]
    self.assertGreater(len(long_routes), 1)
    legacy_max = visible_max + 2 + 2 * (len(long_routes) - 1)
    self.assertLess(layout.max_y, legacy_max)
    self.assertEqual(
      {(route.source, route.target) for route in layout.routes},
      set(edges),
    )


if __name__ == "__main__":
  unittest.main()
