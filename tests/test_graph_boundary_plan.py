from __future__ import annotations

import unittest

from repo_workflow.graph_boundary_plan import (
  dogleg_edges,
  dogleg_route_rows,
  long_bridge_edges,
)
from repo_workflow.graph_render_model import Graph, GraphSiblings, ValidatedGraph
from repo_workflow.graph_render_types import Placement, SemanticEdge


def plain(text: str) -> str:
  return text


def edge(source: str, target: str) -> SemanticEdge:
  return SemanticEdge(
    source,
    target,
    GraphSiblings((source,)),
    GraphSiblings((target,)),
    None,
    plain,
  )


class BoundaryPlanTests(unittest.TestCase):
  def test_adjacent_fan_out_only_edge_requires_dogleg(self):
    item = edge("A", "B")
    validated = ValidatedGraph(
      graph=Graph((), (), plain, lambda entries: None),
      node_group={},
      node_lane={},
      adjacency={
        "A": frozenset({"B", "C"}),
        "B": frozenset(),
        "C": frozenset(),
      },
      incoming={
        "A": frozenset(),
        "B": frozenset({"A"}),
        "C": frozenset({"A"}),
      },
    )
    placements = {
      "A": Placement(0, 0),
      "B": Placement(1, 0),
      "C": Placement(1, 1),
    }

    self.assertEqual(
      dogleg_edges(validated, (item,), placements, set()),
      {item.key},
    )

  def test_adjacent_fan_in_only_edge_requires_dogleg(self):
    item = edge("A", "C")
    validated = ValidatedGraph(
      graph=Graph((), (), plain, lambda entries: None),
      node_group={},
      node_lane={},
      adjacency={
        "A": frozenset({"C"}),
        "B": frozenset({"C"}),
        "C": frozenset(),
      },
      incoming={
        "A": frozenset(),
        "B": frozenset(),
        "C": frozenset({"A", "B"}),
      },
    )
    placements = {
      "A": Placement(0, 0),
      "B": Placement(0, 1),
      "C": Placement(1, 0),
    }

    self.assertEqual(
      dogleg_edges(validated, (item,), placements, set()),
      {item.key},
    )

  def test_different_row_dogleg_uses_source_row(self):
    item = edge("A", "B")
    placements = {
      "A": Placement(0, 3),
      "B": Placement(1, 7),
    }

    self.assertEqual(
      dogleg_route_rows((item,), {item.key}, placements, 7),
      {item.key: 3},
    )

  def test_same_row_doglegs_receive_distinct_private_rows(self):
    first = edge("A", "B")
    second = edge("C", "D")
    placements = {
      "A": Placement(0, 2),
      "B": Placement(1, 2),
      "C": Placement(0, 4),
      "D": Placement(1, 4),
    }

    rows = dogleg_route_rows(
      (first, second),
      {first.key, second.key},
      placements,
      4,
    )

    self.assertEqual(set(rows.values()), {5, 6})
    self.assertEqual(rows[first.key], 5)
    self.assertEqual(rows[second.key], 6)

  def test_long_fan_in_only_edge_requires_endpoint_separation(self):
    item = edge("A", "D")
    validated = ValidatedGraph(
      graph=Graph((), (), plain, lambda entries: None),
      node_group={},
      node_lane={},
      adjacency={
        "A": frozenset({"D"}),
        "B": frozenset({"D"}),
        "D": frozenset(),
      },
      incoming={
        "A": frozenset(),
        "B": frozenset(),
        "D": frozenset({"A", "B"}),
      },
    )
    placements = {
      "A": Placement(0, 0),
      "B": Placement(0, 1),
      "D": Placement(2, 0),
    }

    self.assertEqual(
      long_bridge_edges(validated, (item,), placements, set()),
      {item.key},
    )

  def test_different_row_many_to_many_bridge_requires_dogleg(self):
    bridge = edge("S", "T")
    edges = (
      edge("A", "T"),
      bridge,
      edge("S", "U"),
    )
    validated = ValidatedGraph(
      graph=Graph((), (), plain, lambda entries: None),
      node_group={},
      node_lane={},
      adjacency={
        "A": frozenset({"T"}),
        "S": frozenset({"T", "U"}),
        "T": frozenset(),
        "U": frozenset(),
      },
      incoming={
        "A": frozenset(),
        "S": frozenset(),
        "T": frozenset({"A", "S"}),
        "U": frozenset({"S"}),
      },
    )
    placements = {
      "A": Placement(0, 0),
      "S": Placement(0, 5),
      "T": Placement(1, 1),
      "U": Placement(1, 6),
    }

    result = dogleg_edges(
      validated,
      edges,
      placements,
      set(),
    )

    self.assertIn(bridge.key, result)


if __name__ == "__main__":
  unittest.main()
