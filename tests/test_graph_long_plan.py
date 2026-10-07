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
  return SemanticEdge(
    source,
    target,
    GraphSiblings((source,)),
    GraphSiblings((target,)),
    None,
    plain,
  )


def validated_stub() -> ValidatedGraph:
  graph = Graph(
    (),
    (Lane(("A",), plain),),
    plain,
    lambda entries: None,
  )
  return ValidatedGraph(
    graph=graph,
    node_group={},
    adjacency={},
    incoming={},
    node_lane={},
  )


class LongRoutePlannerTests(unittest.TestCase):
  def test_prefers_first_semantically_valid_compact_candidate(self):
    item = semantic_edge("A", "B")
    placements = {
      "A": Placement(0, 0),
      "B": Placement(2, 2),
    }
    columns = {
      0: Column(("A",), ("A",), 1),
      1: Column(("X",), ("X",), 1),
      2: Column(("B",), ("B",), 1),
    }

    with (
      patch(
        "repo_workflow.graph_long_plan.long_route_candidates",
        return_value=(0, 2),
      ),
      patch(
        "repo_workflow.graph_long_plan.long_route_candidate_valid",
        side_effect=lambda edge, row, *args, **kwargs: row == 2,
      ),
      patch("repo_workflow.graph_long_plan.route_long"),
    ):
      _, routes = route_long_edges(
        [item],
        cells={},
        routes=[],
        validated=validated_stub(),
        placements=placements,
        columns=columns,
        starts={0: 0, 1: 4, 2: 8},
        tracks={},
        max_node_row=2,
        used_rows={},
      )

    self.assertEqual(routes[0].hidden[0].row, 2)

  def test_uses_private_row_when_compact_candidates_are_unsafe(self):
    item = semantic_edge("A", "B")
    placements = {
      "A": Placement(0, 0),
      "B": Placement(2, 2),
    }
    columns = {
      0: Column(("A",), ("A",), 1),
      1: Column(("X",), ("X",), 1),
      2: Column(("B",), ("B",), 1),
    }

    checked = []

    def valid(edge, row, *args, **kwargs):
      checked.append(row)
      return row == 3

    with (
      patch(
        "repo_workflow.graph_long_plan.long_route_candidates",
        return_value=(0, 2),
      ),
      patch(
        "repo_workflow.graph_long_plan.long_route_candidate_valid",
        side_effect=valid,
      ),
      patch("repo_workflow.graph_long_plan.route_long"),
    ):
      _, routes = route_long_edges(
        [item],
        cells={},
        routes=[],
        validated=validated_stub(),
        placements=placements,
        columns=columns,
        starts={0: 0, 1: 4, 2: 8},
        tracks={},
        max_node_row=2,
        used_rows={},
      )

    self.assertEqual(checked, [0, 2, 3])
    self.assertEqual(routes[0].hidden[0].row, 3)

  def test_private_rows_are_unique_and_deterministic(self):
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

    with (
      patch(
        "repo_workflow.graph_long_plan.long_route_candidates",
        return_value=(),
      ),
      patch(
        "repo_workflow.graph_long_plan.long_route_candidate_valid",
        return_value=True,
      ),
      patch("repo_workflow.graph_long_plan.route_long"),
    ):
      _, routes = route_long_edges(
        [second, first],
        cells={},
        routes=[],
        validated=validated_stub(),
        placements=placements,
        columns=columns,
        starts={0: 0, 1: 4, 2: 8},
        tracks={},
        max_node_row=1,
        used_rows={},
      )

    rows = {
      (route.source, route.target): route.hidden[0].row
      for route in routes
    }
    self.assertEqual(rows[first.key], 2)
    self.assertEqual(rows[second.key], 3)


if __name__ == "__main__":
  unittest.main()
