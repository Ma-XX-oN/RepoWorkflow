from __future__ import annotations

import unittest

from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  GraphLayoutError,
  SemanticEdge,
)
from repo_workflow.graph_route_interactions import switch_edges_for_cell
from repo_workflow.graph_route_path import simple_path


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


class GraphRouteSemanticTests(unittest.TestCase):
  def test_adjacent_parallel_dogleg_legs_are_not_connected_without_bits(self):
    route = {
      (0, 0): _R,
      (1, 0): _L | _D,
      (1, 1): _U | _D,
      (1, 2): _U | _D,
      (1, 3): _U | _R,
      (2, 3): _L | _U,
      (2, 2): _U | _D,
      (2, 1): _U | _D,
      (2, 0): _D | _R,
      (3, 0): _L,
    }

    path = simple_path(route, (0, 0), (3, 0))

    self.assertEqual(len(path), len(route))
    self.assertEqual(path[0], (0, 0))
    self.assertEqual(path[-1], (3, 0))

  def test_direction_bits_detect_real_cross_connection(self):
    route = {
      (0, 0): _R,
      (1, 0): _L | _D,
      (1, 1): _U | _D | _R,
      (1, 2): _U | _D,
      (1, 3): _U | _R,
      (2, 3): _L | _U,
      (2, 2): _U | _D,
      (2, 1): _U | _D | _L,
      (2, 0): _D | _R,
      (3, 0): _L,
    }

    with self.assertRaisesRegex(
      GraphLayoutError,
      "branches or self-intersects",
    ):
      simple_path(route, (0, 0), (3, 0))

  def test_perpendicular_same_source_crossing_is_not_a_switch(self):
    left = edge("S", "A")
    down = edge("S", "B")
    self.assertEqual(
      switch_edges_for_cell((
        Contribution(left, _L | _R),
        Contribution(down, _U | _D),
      )),
      set(),
    )

  def test_perpendicular_same_target_crossing_is_not_a_switch(self):
    left = edge("A", "T")
    down = edge("B", "T")
    self.assertEqual(
      switch_edges_for_cell((
        Contribution(left, _L | _R),
        Contribution(down, _U | _D),
      )),
      set(),
    )

  def test_shared_direction_same_source_overlap_is_a_switch(self):
    first = edge("S", "A")
    second = edge("S", "B")
    self.assertEqual(
      switch_edges_for_cell((
        Contribution(first, _L | _R),
        Contribution(second, _R | _D),
      )),
      {first.key, second.key},
    )

  def test_shared_direction_same_target_overlap_is_a_switch(self):
    first = edge("A", "T")
    second = edge("B", "T")
    self.assertEqual(
      switch_edges_for_cell((
        Contribution(first, _L | _R),
        Contribution(second, _L | _U),
      )),
      {first.key, second.key},
    )

  def test_bundle_identity_is_an_explicit_switch_contract(self):
    first = edge("A", "X")
    second = edge("B", "Y")
    bundle = (1, 2)
    self.assertEqual(
      switch_edges_for_cell((
        Contribution(first, _L | _R, bundle),
        Contribution(second, _U | _D, bundle),
      )),
      {first.key, second.key},
    )


if __name__ == "__main__":
  unittest.main()
