from __future__ import annotations

import unittest

from repo_workflow.graph_render import _render_cell
from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  SemanticEdge,
)
from repo_workflow.graph_route_interactions import switch_edges_for_cell


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


class GraphCellSemanticTests(unittest.TestCase):
  def test_same_source_perpendicular_crossing_is_not_a_junction(self):
    first = edge("A", "B")
    second = edge("A", "C")
    contributions = (
      Contribution(first, _L | _R),
      Contribution(second, _U | _D, vertical_direction=1),
    )

    self.assertEqual(switch_edges_for_cell(contributions), set())
    self.assertEqual(_render_cell(list(contributions), plain), "─")

  def test_same_target_perpendicular_crossing_is_not_a_junction(self):
    first = edge("A", "C")
    second = edge("B", "C")
    contributions = (
      Contribution(first, _L | _R),
      Contribution(second, _U | _D, vertical_direction=-1),
    )

    self.assertEqual(switch_edges_for_cell(contributions), set())
    self.assertEqual(_render_cell(list(contributions), plain), "─")

  def test_same_source_shared_direction_remains_a_junction(self):
    first = edge("A", "B")
    second = edge("A", "C")
    contributions = (
      Contribution(first, _L | _R),
      Contribution(second, _L | _D, vertical_direction=1),
    )

    self.assertEqual(
      switch_edges_for_cell(contributions),
      {first.key, second.key},
    )
    self.assertEqual(_render_cell(list(contributions), plain), "┬")

  def test_same_target_shared_direction_remains_a_junction(self):
    first = edge("A", "C")
    second = edge("B", "C")
    contributions = (
      Contribution(first, _L | _R),
      Contribution(second, _R | _U, vertical_direction=-1),
    )

    self.assertEqual(
      switch_edges_for_cell(contributions),
      {first.key, second.key},
    )
    self.assertEqual(_render_cell(list(contributions), plain), "┴")


if __name__ == "__main__":
  unittest.main()
