"""#583 independent monochrome and accessible state-glyph rendering."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_diagnostics import LaneDiagnostics
from repo_workflow.lane_render import render_lanes, set_color_setting
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.public_cli import _handle_lanes
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from repo_workflow.terminal_style import TerminalStyler
from tests.support import RepoFixture


class TerminalStateAccessibilityAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("verifier", "session")
    self.relationships = RelationshipStore(self.root)
    self.relationships.create(RelationshipGraph(issues={
      "1": IssueRelationships("Long " + "x" * 120, ()),
      "2": IssueRelationships("Feature: " + "y" * 120, ("1",)),
    }), self.writer)
    LaneSelectionStore(self.root).select((2,), self.writer)
    IssueMetadataStore(self.root).write({
      1: IssueMetadata(
        number=1, title="Initiative: " + "a" * 120,
        state="closed", link="https://example.invalid/1",
      ),
      2: IssueMetadata(
        number=2, title="Feature: " + "b" * 120,
        state="open", link="https://example.invalid/2",
      ),
    }, self.writer)

  def tearDown(self):
    self.temp.cleanup()

  def test_monochrome_unknown_and_accessible_legend_are_stable(self):
    # G13: unknown status and six labels distinguish states without colour.
    set_color_setting(self.root, "never", self.writer)
    original = self.relationships.path.read_bytes()
    unknown = "\n".join(render_lanes(self.root))
    self.assertIn("?", unknown)
    self.assertNotIn("\x1b[", unknown)
    lifecycle = LifecycleStore(self.root)
    lifecycle.transition(1, "start", "candidate-1", 0, self.writer, None)
    lifecycle.transition(2, "start", "candidate-2", 0, self.writer, None)
    lifecycle.transition(2, "abort", "candidate-2", 0, self.writer, 0)
    self.relationships.refresh_states(self.writer)
    snapshot = self.relationships.path.read_bytes()
    first = "\n".join(render_lanes(self.root))
    for _ in range(4):
      self.assertEqual("\n".join(render_lanes(self.root)), first)
    self.assertIn("●", first)
    self.assertIn("✕", first)
    self.assertIn("I:", first)
    self.assertIn("F:", first)
    self.assertNotIn("\x1b[", first)
    for glyph in "○●◎✓♥✕?":
      self.assertEqual(TerminalStyler("never").display_width(glyph), 1)

    output = StringIO()
    with redirect_stdout(output):
      self.assertEqual(
        _handle_lanes(
          self.root, ["lanes", "view", "--legend"],
          LaneDiagnostics(self.root, ("lanes", "view", "--legend")),
        ), 0,
      )
    rendered = output.getvalue()
    self.assertIn(first, rendered)
    for state in (
      "not_started", "active", "in_review", "accepted", "completed", "aborted",
    ):
      self.assertIn(state, rendered)
    self.assertIn("Legend:", rendered)
    self.assertNotIn("\x1b[", rendered)
    self.assertEqual(self.relationships.path.read_bytes(), snapshot)
    self.assertNotEqual(snapshot, original)


if __name__ == "__main__":
  unittest.main()
