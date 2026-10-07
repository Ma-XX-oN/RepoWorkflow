from __future__ import annotations

from unittest.mock import patch
import unittest

from repo_workflow.graph_boundary_order import order_boundary_items
from repo_workflow.graph_render_model import (
  Graph,
  GraphSiblings,
  Lane,
  ValidatedGraph,
)
from repo_workflow.graph_render_types import Column, Placement, SemanticEdge


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


class BoundaryOrderTests(unittest.TestCase):
  def test_prefers_better_semantically_valid_track_order(self):
    first = edge("A", "B")
    second = edge("C", "D")
    first_item = ("edge", "A", "B")
    second_item = ("edge", "C", "D")
    placements = {
      "A": Placement(0, 0),
      "B": Placement(1, 0),
      "C": Placement(0, 1),
      "D": Placement(1, 1),
    }
    validated = ValidatedGraph(
      graph=Graph(
        (),
        (Lane(("A",), plain), Lane(("C",), plain)),
        plain,
        lambda entries: None,
      ),
      node_group={},
      adjacency={
        "A": frozenset({"B"}),
        "B": frozenset(),
        "C": frozenset({"D"}),
        "D": frozenset(),
      },
      incoming={
        "A": frozenset(),
        "B": frozenset({"A"}),
        "C": frozenset(),
        "D": frozenset({"C"}),
      },
      node_lane={},
    )

    def quality(order, *args, **kwargs):
      if order == (first_item, second_item):
        return 1, 1, 0
      return 0, 0, 0

    with (
      patch(
        "repo_workflow.graph_boundary_order._order_is_valid",
        return_value=True,
      ),
      patch(
        "repo_workflow.graph_boundary_order._boundary_order_quality",
        side_effect=quality,
      ),
    ):
      result = order_boundary_items(
        {first_item, second_item},
        0,
        (first, second),
        placements,
        {
          0: Column(("A", "C"), ("A", "C"), 1),
          1: Column(("B", "D"), ("B", "D"), 1),
        },
        validated,
        set(),
        set(),
        set(),
        {},
      )

    self.assertEqual(result, (second_item, first_item))

  def test_passive_long_tracks_do_not_enter_adjacent_semantic_search(self):
    adjacent = edge("A", "B")
    passive_source = ("dogleg-source", "L1", "L2")
    passive_target = ("dogleg-target", "L1", "L2")
    active_item = ("edge", "A", "B")
    items = {passive_source, active_item, passive_target}
    placements = {
      "A": Placement(0, 0),
      "B": Placement(1, 0),
      "L1": Placement(0, 1),
      "L2": Placement(2, 1),
    }
    validated = ValidatedGraph(
      graph=Graph((), (Lane(("A",), plain),), plain, lambda entries: None),
      node_group={},
      adjacency={"A": frozenset({"B"}), "B": frozenset()},
      incoming={"A": frozenset(), "B": frozenset({"A"})},
      node_lane={},
    )
    seen = []

    def valid(order, *args, **kwargs):
      seen.append(order)
      return True

    with patch(
      "repo_workflow.graph_boundary_order._order_is_valid",
      side_effect=valid,
    ):
      result = order_boundary_items(
        items,
        0,
        (adjacent,),
        placements,
        {0: Column(("A",), ("A",), 1), 1: Column(("B",), ("B",), 1)},
        validated,
        set(),
        set(),
        set(),
        {},
      )

    self.assertEqual(seen, [(active_item,)])
    self.assertEqual(set(result), items)
    self.assertEqual(
      tuple(item for item in result if item == active_item),
      (active_item,),
    )


if __name__ == "__main__":
  unittest.main()
