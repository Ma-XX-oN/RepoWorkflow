from __future__ import annotations

from unittest.mock import patch
import unittest

from repo_workflow.graph_long_plan import route_long_edges
from repo_workflow.graph_render_model import (
  Graph,
  GraphSiblings,
  Lane,
  ValidatedGraph,
)
from repo_workflow.graph_render_types import (
  Column,
  Placement,
  SemanticEdge,
)


def plain(text: str) -> str:
  return text


def semantic_edge(source: str, target: str) -> SemanticEdge:
  source_group = GraphSiblings((source,))
  target_group = GraphSiblings((target,))
  return SemanticEdge(
    source,
    target,
    source_group,
    target_group,
    None,
    plain,
  )


class LongRoutePlannerTests(unittest.TestCase):
  def test_backtracks_when_first_local_choice_blocks_later_edge(self):
    first = semantic_edge("A", "B")
    second = semantic_edge("C", "D")
    placements = {
      "A": Placement(0, 0),
      "B": Placement(2, 0),
      "C": Placement(0, 1),
      "D": Placement(2, 1),
    }
    columns = {
      0: Column(("A", "C"), ("A", "C"), 1),
      1: Column(("X",), ("X",), 1),
      2: Column(("B", "D"), ("B", "D"), 1),
    }
    graph = Graph(
      (),
      (Lane(("A",), plain),),
      plain,
      lambda entries: None,
    )
    validated = ValidatedGraph(
      graph=graph,
      node_group={},
      adjacency={},
      incoming={},
      node_lane={},
    )

    def candidates(edge, *args, **kwargs):
      return (0, 1)

    def candidate_valid(
      edge,
      row,
      cells,
      routes,
      *args,
      **kwargs,
    ):
      if edge.key == first.key:
        return True
      return bool(
        row == 0
        and routes
        and routes[0].hidden
        and routes[0].hidden[0].row == 1
      )

    with (
      patch(
        "repo_workflow.graph_long_plan.long_route_candidates",
        side_effect=candidates,
      ),
      patch(
        "repo_workflow.graph_long_plan.long_route_candidate_valid",
        side_effect=candidate_valid,
      ),
      patch("repo_workflow.graph_long_plan.route_long"),
    ):
      _, routes = route_long_edges(
        [first, second],
        cells={},
        routes=[],
        validated=validated,
        placements=placements,
        columns=columns,
        starts={0: 0, 1: 4, 2: 8},
        tracks={},
        max_node_row=1,
        used_rows={},
      )

    self.assertEqual(routes[0].hidden[0].row, 1)
    self.assertEqual(routes[1].hidden[0].row, 0)


if __name__ == "__main__":
  unittest.main()
