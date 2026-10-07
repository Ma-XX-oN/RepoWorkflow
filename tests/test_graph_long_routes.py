from __future__ import annotations

import unittest

from repo_workflow.graph_long_routes import (
  choose_long_route_row,
  long_route_candidates,
)
from repo_workflow.graph_render_model import GraphSiblings
from repo_workflow.graph_render_types import GraphLayoutError, Placement, SemanticEdge


def identity(text: str) -> str:
  return text


def edge_between(source_name: str, target_name: str) -> SemanticEdge:
  source = GraphSiblings((source_name,))
  target = GraphSiblings((target_name,))
  return SemanticEdge(
    source_name,
    target_name,
    source,
    target,
    None,
    identity,
  )


def edge() -> SemanticEdge:
  return edge_between("A", "B")


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

  def test_disjoint_spans_may_reuse_same_row(self):
    candidate = edge_between("A", "B")
    existing = edge_between("C", "D")
    placements = {
      "A": Placement(0, 7),
      "B": Placement(2, 7),
      "C": Placement(3, 0),
      "D": Placement(5, 0),
    }
    rows = long_route_candidates(
      candidate,
      placements,
      7,
      {7: [existing]},
      lambda row: 0,
    )
    self.assertIn(7, rows)

  def test_overlapping_unrelated_spans_cannot_reuse_same_row(self):
    candidate = edge_between("A", "B")
    existing = edge_between("C", "D")
    placements = {
      "A": Placement(0, 7),
      "B": Placement(2, 7),
      "C": Placement(1, 0),
      "D": Placement(3, 0),
    }
    rows = long_route_candidates(
      candidate,
      placements,
      7,
      {7: [existing]},
      lambda row: 0,
    )
    self.assertNotIn(7, rows)

  def test_overlap_component_rejects_merge_after_branch_chain(self):
    candidate = edge_between("A", "X")
    same_source = edge_between("A", "Y")
    same_target = edge_between("B", "X")
    placements = {
      "A": Placement(0, 7),
      "X": Placement(3, 7),
      "Y": Placement(2, 0),
      "B": Placement(2, 1),
    }
    rows = long_route_candidates(
      candidate,
      placements,
      7,
      {7: [same_source, same_target]},
      lambda row: 0,
    )
    self.assertNotIn(7, rows)

  def test_all_unsafe_candidates_fail_explicitly(self):
    checked = []

    def invalid(row):
      checked.append(row)
      return False

    with self.assertRaisesRegex(
      GraphLayoutError,
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
