from __future__ import annotations

import unittest

from repo_workflow.graph_boundary_plan import dogleg_edges
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
