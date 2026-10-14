from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.command_grammar import Context, parse_tokens
from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_diagnostics import LaneDiagnostics
from repo_workflow.lane_render import render_lanes
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.public_cli import _handle_lanes
from repo_workflow.public_commands import COMMANDS
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from repo_workflow.terminal_style import TerminalStyler
from tests.support import RepoFixture


class SixStateGraphIntegrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")
    self.relationships = RelationshipStore(self.root)
    self.relationships.create(
      RelationshipGraph(issues={
        str(issue): IssueRelationships(
          f"Ticket {issue}",
          () if issue == 1 else (str(issue - 1),),
        )
        for issue in range(1, 7)
      }),
      self.writer,
    )
    LaneSelectionStore(self.root).select((6,), self.writer)
    IssueMetadataStore(self.root).write(
      {
        issue: IssueMetadata(
          number=issue,
          title=f"Ticket {issue}",
          state="closed",
          link=f"https://example.invalid/{issue}",
        )
        for issue in range(1, 7)
      },
      self.writer,
    )

  def tearDown(self):
    self.temp.cleanup()

  def advance(self, issue, transitions):
    store = LifecycleStore(self.root)
    snapshot = store.read(issue)
    for transition in transitions:
      snapshot = store.transition(
        issue,
        transition,
        f"candidate-{issue}",
        0,
        self.writer,
        snapshot.revision,
      )
    return snapshot

  def seed_all_states(self):
    self.advance(2, ("start",))
    self.advance(3, ("start", "submit-review"))
    self.advance(4, ("start", "submit-review", "accept"))
    self.advance(5, ("start", "submit-review", "accept", "complete"))
    self.advance(6, ("start", "abort"))

  def test_graph_uses_cached_states_until_explicit_refresh(self):
    self.seed_all_states()
    path = self.relationships.path
    original = path.read_bytes()
    before = "\n".join(render_lanes(self.root))
    self.assertEqual(before.count("?"), 6)
    self.assertEqual(path.read_bytes(), original)

    parse_tokens(
      COMMANDS,
      Context(self.root, legal_only=False),
      ["lanes", "view", "--current"],
    )
    output = StringIO()
    with patch(
      "repo_workflow.public_cli.runtime_writer_identity",
      return_value=self.writer,
    ):
      with redirect_stdout(output):
        _handle_lanes(
          self.root,
          ["lanes", "view", "--current"],
          LaneDiagnostics(self.root, ("lanes", "view", "--current")),
        )

    saved = self.relationships.read()
    self.assertIsNotNone(saved.states)
    self.assertEqual(
      {issue: item.state for issue, item in saved.states.items()},
      {
        "1": "not_started",
        "2": "active",
        "3": "in_review",
        "4": "accepted",
        "5": "completed",
        "6": "aborted",
      },
    )
    result = output.getvalue()
    for glyph in "○●◎✓♥✕":
      self.assertIn(glyph, result)
    self.assertNotIn("?", result)
    self.assertIn("state,state_revision", path.read_text(encoding="utf-8"))
    self.assertEqual("\n".join(render_lanes(self.root)), result.rstrip())

  def test_refresh_failure_does_not_mutate_csv(self):
    self.seed_all_states()
    original = self.relationships.path.read_bytes()
    with patch(
      "repo_workflow.relationship_store.LifecycleStore.read",
      side_effect=RuntimeError("unavailable"),
    ):
      with self.assertRaisesRegex(RuntimeError, "unavailable"):
        self.relationships.refresh_states(self.writer)
    self.assertEqual(self.relationships.path.read_bytes(), original)

  def test_symbols_use_one_terminal_cell(self):
    terminal = TerminalStyler("never")
    for glyph in "○●◎✓♥✕":
      with self.subTest(glyph=glyph):
        self.assertEqual(terminal.display_width(glyph), 1)


if __name__ == "__main__":
  unittest.main()
