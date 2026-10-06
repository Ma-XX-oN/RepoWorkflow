import re
import unittest

from repo_workflow.graph_render import render_graph
from repo_workflow.graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphSiblings,
  Lane,
)


def marker(name):
  def apply(text: str) -> str:
    return f"<{name}>{text}</{name}>"
  return apply


RED = marker("red")
BLUE = marker("blue")
GREEN = marker("green")
GREY = marker("grey")


def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
  width = max((len(entry.raw_text) for entry in entries), default=0)
  return AlignedColumn(
    tuple(entry.colour(entry.raw_text.ljust(width)) for entry in entries),
    width,
  )


def plain(lines):
  return tuple(
    re.sub(r"</?[^>]+>", "", line)
    for line in lines
  )


class GraphRenderTests(unittest.TestCase):
  def test_empty_graph_renders_nothing(self):
    result = render_graph(Graph((), (), GREY, formatter))
    self.assertEqual(result.lines, ())
    self.assertEqual(result.routes, ())

  def test_siblings_remain_compact_and_share_target(self):
    x = GraphSiblings(("X",))
    siblings = GraphSiblings(("C", "A"), (x,))
    graph = Graph(
      (x, siblings),
      (
        Lane(("A", "X"), RED),
        Lane(("C",), BLUE),
      ),
      GREY,
      formatter,
    )
    result = render_graph(graph)
    text = "\n".join(plain(result.lines))
    self.assertEqual(text.count("A"), 1)
    self.assertEqual(text.count("C"), 1)
    self.assertEqual(text.count("X"), 1)
    self.assertIn("┬", text)
    rendered = "\n".join(result.lines)
    self.assertIn("<red>", rendered)
    self.assertNotIn("<grey>", rendered)
    self.assertEqual(
      {(route.source, route.target) for route in result.routes},
      {("A", "X"), ("C", "X")},
    )

  def test_long_edge_records_hidden_semantic_endpoints(self):
    p = GraphSiblings(("P",))
    x = GraphSiblings(("X",), (p,))
    a = GraphSiblings(("A",), (x, p))
    graph = Graph(
      (a, x, p),
      (Lane(("A", "X", "P"), RED),),
      GREY,
      formatter,
    )
    result = render_graph(graph)
    long_route = next(
      route
      for route in result.routes
      if (route.source, route.target) == ("A", "P")
    )
    self.assertEqual(long_route.kind, "long")
    self.assertEqual(
      [
        (
          item.semantic_source,
          item.semantic_target,
          item.column,
        )
        for item in long_route.hidden
      ],
      [("A", "P", 1)],
    )
    self.assertIn("<red>", "\n".join(result.lines))

  def test_directional_cousin_routes_emit_vertical_arrows(self):
    x = GraphSiblings(("X",))
    y = GraphSiblings(("Y",))
    a = GraphSiblings(("A",), (x,))
    b = GraphSiblings(("B",), (x, y))
    c = GraphSiblings(("C",), (y,))
    result = render_graph(
      Graph(
        (a, b, c, x, y),
        (
          Lane(("A", "X"), RED),
          Lane(("B",), BLUE),
          Lane(("C", "Y"), GREEN),
        ),
        GREY,
        formatter,
      )
    )
    rendered = "\n".join(plain(result.lines))
    self.assertTrue("↑" in rendered or "↓" in rendered)
    self.assertEqual(
      {(route.source, route.target) for route in result.routes},
      {
        ("A", "X"),
        ("B", "X"),
        ("B", "Y"),
        ("C", "Y"),
      },
    )

  def test_multi_overlap_preserves_lane_and_default_edge_colours(self):
    x = GraphSiblings(("X",))
    y = GraphSiblings(("Y",))
    z = GraphSiblings(("Z",))
    a = GraphSiblings(("A",), (x,))
    b = GraphSiblings(("B",), (x, y, z))
    c = GraphSiblings(("C",), (y,))
    d = GraphSiblings(("D",), (z,))
    result = render_graph(
      Graph(
        (a, b, c, d, x, y, z),
        (
          Lane(("A", "X"), RED),
          Lane(("B", "Z"), BLUE),
          Lane(("C", "Y"), GREEN),
          Lane(("D",), marker("yellow")),
        ),
        GREY,
        formatter,
      )
    )
    rendered = "\n".join(result.lines)
    self.assertIn("<red>", rendered)
    self.assertIn("<blue>", rendered)
    self.assertIn("<green>", rendered)
    self.assertIn("<grey>", rendered)
    self.assertEqual(
      {(route.source, route.target) for route in result.routes},
      {
        ("A", "X"),
        ("B", "X"),
        ("B", "Y"),
        ("B", "Z"),
        ("C", "Y"),
        ("D", "Z"),
      },
    )

  def test_cross_lane_edge_uses_default_colour(self):
    x = GraphSiblings(("X",))
    a = GraphSiblings(("A",), (x,))
    result = render_graph(
      Graph(
        (a, x),
        (Lane(("A",), RED), Lane(("X",), BLUE)),
        GREY,
        formatter,
      )
    )
    rendered = "\n".join(result.lines)
    self.assertIn("<red>A", rendered)
    self.assertIn("<blue>X", rendered)
    self.assertIn("<grey>", rendered)

  def test_same_lane_edge_uses_lane_colour(self):
    x = GraphSiblings(("X",))
    a = GraphSiblings(("A",), (x,))
    result = render_graph(
      Graph(
        (a, x),
        (Lane(("A", "X"), GREEN),),
        GREY,
        formatter,
      )
    )
    rendered = "\n".join(result.lines)
    self.assertNotIn("<grey>", rendered)
    self.assertIn("<green>", rendered)

  def test_input_order_does_not_change_output(self):
    p = GraphSiblings(("P",))
    x = GraphSiblings(("X",), (p,))
    a = GraphSiblings(("A",), (x,))
    b = GraphSiblings(("B",), (p,))
    lane_a = Lane(("A", "X", "P"), RED)
    lane_b = Lane(("B",), BLUE)
    first = render_graph(
      Graph((a, b, x, p), (lane_a, lane_b), GREY, formatter)
    )
    second = render_graph(
      Graph((p, x, b, a), (lane_b, lane_a), GREY, formatter)
    )
    self.assertEqual(first.lines, second.lines)
    self.assertEqual(first.routes, second.routes)

  def test_formatter_controls_encoded_text_and_display_width(self):
    calls = []

    def custom(entries):
      calls.append(tuple(entry.raw_text for entry in entries))
      width = max(len(entry.raw_text) for entry in entries)
      return AlignedColumn(
        tuple(
          entry.colour(entry.raw_text.center(width))
          for entry in entries
        ),
        width,
      )

    group = GraphSiblings(("A", "LONG"))
    result = render_graph(
      Graph(
        (group,),
        (Lane(("A",), RED), Lane(("LONG",), BLUE)),
        GREY,
        custom,
      )
    )
    self.assertEqual(calls, [("A", "LONG")])
    self.assertEqual(plain(result.lines), (" A  ", "LONG"))

  def test_disconnected_components_are_rendered_once(self):
    a = GraphSiblings(("A",))
    b = GraphSiblings(("B",))
    result = render_graph(
      Graph(
        (b, a),
        (Lane(("A",), RED), Lane(("B",), BLUE)),
        GREY,
        formatter,
      )
    )
    text = "\n".join(plain(result.lines))
    self.assertEqual(text.count("A"), 1)
    self.assertEqual(text.count("B"), 1)


if __name__ == "__main__":
  unittest.main()
