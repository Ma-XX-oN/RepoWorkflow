"""#583 independent graph adapter determinism across relevant layouts."""

import unittest

from repo_workflow.graph_render import render_graph
from repo_workflow.lane_graph_adapter import project_lane_graph
from repo_workflow.lane_selection import LaneSelection
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.terminal_style import TerminalStyler


class SixStateGraphLayoutStability(unittest.TestCase):
  def project(self, graph, assignment, states):
    selection = LaneSelection(
      roots=(max(graph.issues, key=int),),
      closure=tuple(sorted(graph.issues, key=int)),
      graph_revision=1,
      assignment=assignment,
    )
    metadata = {
      issue: {
        "title": (
          "Initiative: " if int(issue) % 2 else "Feature: "
        ) + ("long title " * 20),
        "closed": False,
        "link": f"https://example.invalid/{issue}",
        "lifecycle_state": states[issue],
      }
      for issue in graph.issues
    }
    styler = TerminalStyler("never")
    lanes = {name: (lambda text: text) for name in set(assignment.values())}
    return project_lane_graph(
      selection, graph, set(graph.issues), metadata,
      lane_colours=lanes,
      default_edge_colour=lambda text: text,
      display_width=styler.display_width,
    )

  def test_chain_and_diamond_with_mixed_states_deterministic(self):
    cases = (
      (
        {
          "1": IssueRelationships("One", ()),
          "2": IssueRelationships("Two", ("1",)),
          "3": IssueRelationships("Three", ("2",)),
        },
        {"1": "A", "2": "A", "3": "A"},
      ),
      (
        {
          "1": IssueRelationships("One", ()),
          "2": IssueRelationships("Two", ("1",)),
          "3": IssueRelationships("Three", ("1",)),
          "4": IssueRelationships("Four", ("2", "3")),
        },
        {"1": "A", "2": "A", "3": "B", "4": "B"},
      ),
    )
    states = ("not_started", "active", "in_review", "accepted")
    for issues, assignment in cases:
      with self.subTest(ids=tuple(issues)):
        left = RelationshipGraph(issues)
        right = RelationshipGraph(dict(reversed(tuple(issues.items()))))
        status = {
          issue: states[(int(issue) - 1) % len(states)]
          for issue in issues
        }
        a = self.project(left, assignment, status)
        b = self.project(right, dict(reversed(tuple(assignment.items()))),
                         status)
        first = render_graph(a.graph)
        second = render_graph(b.graph)
        self.assertEqual(first.lines, second.lines)
        self.assertEqual(a.issue_text, b.issue_text)
        self.assertTrue(first.lines)
        rendered = "\n".join(first.lines)
        self.assertNotIn("\x1b[", rendered)
        for glyph in ("○", "●"):
          self.assertIn(glyph, rendered)
        for _ in range(3):
          self.assertEqual(render_graph(a.graph).lines, first.lines)


if __name__ == "__main__":
  unittest.main()
