from __future__ import annotations

import unittest

from repo_workflow.graph_long_routes import choose_long_route_row
from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import Placement, SemanticEdge


def identity(text: str) -> str:
  return text


def edge() -> SemanticEdge:
  source = GraphSiblings(("A",))
  target = GraphSiblings(("B",))
  return SemanticEdge(
    "A",
    "B",
    source,
    target,
    None,
    identity,
  )


class LongRouteCandidateTests(unittest.TestCase):
  def setUp(self):
    self.edge = edge()
    self.placements = {
      "A": Placement(0, 0),
      "X": Placement(1, 1),
      "B": Placement(2, 2),
    }

  def test_rejects_better_unsafe_candidate_and_uses_next_valid_row(self):
    checked = []

    def valid(row):
      checked.append(row)
      return row == 2

    chosen = choose_long_route_row(
      self.edge,
      self.placements,
      2,
      {},
      lambda row: 0,
      valid,
    )
    self.assertEqual(chosen, 2)
    self.assertEqual(checked, [0, 2])

  def test_all_unsafe_candidates_fail_explicitly(self):
    checked = []

    def invalid(row):
      checked.append(row)
      return False

    with self.assertRaisesRegex(
      ValueError,
      "no semantically valid bounded long-route row candidate",
    ):
      choose_long_route_row(
        self.edge,
        self.placements,
        2,
        {},
        lambda row: 0,
        invalid,
      )
    self.assertTrue(checked)
    self.assertNotIn(1, checked)


if __name__ == "__main__":
  unittest.main()
