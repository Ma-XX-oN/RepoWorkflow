from __future__ import annotations

import unittest

from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import (
  _D,
  _L,
  _R,
  _U,
  Contribution,
  SemanticEdge,
)
from repo_workflow.graph_route_semantics import _switch_edges


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
  def test_perpendicular_same_source_crossing_is_not_a_switch(self):
    left = edge("S", "A")
    down = edge("S", "B")
    self.assertEqual(
      _switch_edges((
        Contribution(left, _L | _R),
        Contribution(down, _U | _D),
      )),
      set(),
    )

  def test_perpendicular_same_target_crossing_is_not_a_switch(self):
    left = edge("A", "T")
    down = edge("B", "T")
    self.assertEqual(
      _switch_edges((
        Contribution(left, _L | _R),
        Contribution(down, _U | _D),
      )),
      set(),
    )

  def test_shared_direction_same_source_overlap_is_a_switch(self):
    first = edge("S", "A")
    second = edge("S", "B")
    self.assertEqual(
      _switch_edges((
        Contribution(first, _L | _R),
        Contribution(second, _R | _D),
      )),
      {first.key, second.key},
    )

  def test_shared_direction_same_target_overlap_is_a_switch(self):
    first = edge("A", "T")
    second = edge("B", "T")
    self.assertEqual(
      _switch_edges((
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
      _switch_edges((
        Contribution(first, _L | _R, bundle),
        Contribution(second, _U | _D, bundle),
      )),
      {first.key, second.key},
    )


if __name__ == "__main__":
  unittest.main()
