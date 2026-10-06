import unittest

from repo_workflow.graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphInputError,
  GraphSiblings,
  Lane,
  validate_graph,
)


def colour(text: str) -> str:
  return text


def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
  width = max((len(entry.raw_text) for entry in entries), default=0)
  return AlignedColumn(
    tuple(entry.raw_text.ljust(width) for entry in entries),
    width,
  )


class GraphRenderModelTests(unittest.TestCase):
  def graph(self, groups, lanes):
    return Graph(tuple(groups), tuple(lanes), colour, formatter)

  def test_accepts_constrained_sibling_dag(self):
    x = GraphSiblings(("X",))
    siblings = GraphSiblings(("A", "C"), (x,))
    result = validate_graph(
      self.graph(
        (siblings, x),
        (Lane(("A", "X"), colour), Lane(("C",), colour)),
      )
    )
    self.assertEqual(result.adjacency["A"], frozenset({"X"}))
    self.assertEqual(result.adjacency["C"], frozenset({"X"}))

  def test_duplicate_node_text_is_error(self):
    a = GraphSiblings(("A",))
    duplicate = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "duplicate node text"):
      validate_graph(
        self.graph(
          (a, duplicate),
          (Lane(("A",), colour),),
        )
      )

  def test_node_in_two_groups_is_error(self):
    a = GraphSiblings(("A", "B"))
    duplicate = GraphSiblings(("B", "C"))
    with self.assertRaisesRegex(GraphInputError, "duplicate node text"):
      validate_graph(
        self.graph(
          (a, duplicate),
          (
            Lane(("A",), colour),
            Lane(("B",), colour),
            Lane(("C",), colour),
          ),
        )
      )

  def test_duplicate_group_relationship_is_error(self):
    x = GraphSiblings(("X",))
    a = GraphSiblings(("A",), (x, x))
    with self.assertRaisesRegex(GraphInputError, "duplicate GraphSiblings"):
      validate_graph(
        self.graph(
          (a, x),
          (Lane(("A", "X"), colour),),
        )
      )

  def test_target_outside_graph_is_error(self):
    x = GraphSiblings(("X",))
    a = GraphSiblings(("A",), (x,))
    with self.assertRaisesRegex(GraphInputError, "outside the graph"):
      validate_graph(
        self.graph(
          (a,),
          (Lane(("A",), colour),),
        )
      )

  def test_cycle_is_error(self):
    a = GraphSiblings(("A",))
    b = GraphSiblings(("B",))
    a.to_nodes = (b,)
    b.to_nodes = (a,)
    with self.assertRaisesRegex(GraphInputError, "acyclic"):
      validate_graph(
        self.graph(
          (a, b),
          (Lane(("A",), colour), Lane(("B",), colour)),
        )
      )

  def test_node_missing_from_lanes_is_error(self):
    a = GraphSiblings(("A", "B"))
    with self.assertRaisesRegex(GraphInputError, "exactly one lane"):
      validate_graph(
        self.graph(
          (a,),
          (Lane(("A",), colour),),
        )
      )

  def test_node_in_multiple_lanes_is_error(self):
    a = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "multiple lanes"):
      validate_graph(
        self.graph(
          (a,),
          (Lane(("A",), colour), Lane(("A",), colour)),
        )
      )

  def test_unknown_lane_node_is_error(self):
    a = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "unknown node"):
      validate_graph(
        self.graph(
          (a,),
          (Lane(("A", "Z"), colour),),
        )
      )

  def test_lane_must_be_directed_path(self):
    p = GraphSiblings(("P",))
    x = GraphSiblings(("X",), (p,))
    a = GraphSiblings(("A",), (x,))
    with self.assertRaisesRegex(GraphInputError, "not a directed path"):
      validate_graph(
        self.graph(
          (a, x, p),
          (Lane(("A", "P"), colour), Lane(("X",), colour)),
        )
      )

  def test_missing_lane_colour_is_error(self):
    a = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "lane colour"):
      validate_graph(
        Graph(
          (a,),
          (Lane(("A",), None),),
          colour,
          formatter,
        )
      )

  def test_missing_default_edge_colour_is_error(self):
    a = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "default edge colour"):
      validate_graph(
        Graph(
          (a,),
          (Lane(("A",), colour),),
          None,
          formatter,
        )
      )

  def test_missing_formatter_is_error(self):
    a = GraphSiblings(("A",))
    with self.assertRaisesRegex(GraphInputError, "formatter"):
      validate_graph(
        Graph(
          (a,),
          (Lane(("A",), colour),),
          colour,
          None,
        )
      )

  def test_empty_graph_is_valid(self):
    result = validate_graph(Graph((), (), colour, formatter))
    self.assertEqual(result.adjacency, {})


if __name__ == "__main__":
  unittest.main()
