from __future__ import annotations

import unittest

from repo_workflow.graph_route_interactions import interaction_component
from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import Contribution, SemanticEdge


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


class GeometryInteractionTests(unittest.TestCase):
  def test_switch_component_follows_merge_then_branch_chain(self):
    ax = edge("A", "X")
    bx = edge("B", "X")
    by = edge("B", "Y")
    cz = edge("C", "Z")

    cells = {
      (1, 0): [
        Contribution(ax, 1),
        Contribution(bx, 1),
      ],
      (2, 0): [
        Contribution(bx, 1),
        Contribution(by, 1),
      ],
      (3, 0): [
        Contribution(by, 1),
        Contribution(cz, 1),
      ],
    }

    self.assertEqual(
      interaction_component(cells, ax.key),
      {ax.key, bx.key, by.key},
    )


if __name__ == "__main__":
  unittest.main()
