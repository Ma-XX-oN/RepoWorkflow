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
from repo_workflow.relationship_store import RelationshipStore, RelationshipStoreError
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

  def test_authoritative_transition_during_refresh_does_not_publish_stale_state(self):
    # P09: lifecycle revisions must remain valid when CSV is published.
    self.advance(2, ("start",))
    before = self.relationships.path.read_bytes()
    original_read = LifecycleStore.read
    interleaved = False

    def raced_read(store, issue):
      nonlocal interleaved
      sampled = original_read(store, issue)
      if str(issue) == "2" and not interleaved:
        interleaved = True
        LifecycleStore(self.root).transition(
          2, "submit-review", "candidate-2", 0,
          self.writer, sampled.revision,
        )
      return sampled

    with patch(
      "repo_workflow.relationship_store.LifecycleStore.read",
      new=raced_read,
    ):
      try:
        result = self.relationships.refresh_states(self.writer)
      except RelationshipStoreError:
        self.assertEqual(self.relationships.path.read_bytes(), before)
      else:
        self.assertEqual(result.states["2"].state, "in_review")
        self.assertEqual(
          self.relationships.read().states["2"].state, "in_review",
        )
    self.assertTrue(interleaved)
    self.assertEqual(
      LifecycleStore(self.root).read(2).lifecycle.state, "in_review",
    )

  def test_provider_status_crossed_with_six_lifecycles_never_completes_ticket(self):
    # L13: provider open/closed cannot override any of six RWF states.
    self.seed_all_states()
    lifecycle = LifecycleStore(self.root)
    originals = {issue: lifecycle.read(issue) for issue in range(1, 7)}
    expected = {
      1: "not_started", 2: "active", 3: "in_review",
      4: "accepted", 5: "completed", 6: "aborted",
    }
    for provider_state in ("open", "closed"):
      with self.subTest(provider_state=provider_state):
        IssueMetadataStore(self.root).write(
          {
            issue: IssueMetadata(
              number=issue, title=f"Ticket {issue}",
              state=provider_state, link=f"https://example.invalid/{issue}",
            )
            for issue in range(1, 7)
          },
          self.writer,
        )
        snapshot = self.relationships.refresh_states(self.writer)
        self.assertEqual(
          {int(issue): s.state for issue, s in snapshot.states.items()},
          expected,
        )
        self.assertEqual(
          {issue: lifecycle.read(issue) for issue in range(1, 7)},
          originals,
        )
        for issue in range(1, 7):
          self.assertEqual(
            lifecycle.read(issue).lifecycle.dependency_satisfied,
            issue == 5,
          )

  def test_interrupted_csv_replacement_preserves_original_and_cleans_staging(self):
    # P11: failed atomic CSV publication cannot expose partial refresh.
    self.seed_all_states()
    previous_bytes = self.relationships.path.read_bytes()
    previous_readback = self.relationships.read()
    with patch(
      "repo_workflow.relationship_store.os.replace",
      side_effect=OSError("injected CSV publication failure"),
    ):
      with self.assertRaisesRegex(OSError, "injected CSV publication failure"):
        self.relationships.refresh_states(self.writer)
    self.assertEqual(self.relationships.path.read_bytes(), previous_bytes)
    self.assertEqual(self.relationships.read(), previous_readback)
    self.assertEqual(
      list(self.relationships.path.parent.glob(".tickets.csv.*.tmp")), [],
    )

  def test_symbols_use_one_terminal_cell(self):
    terminal = TerminalStyler("never")
    for glyph in "○●◎✓♥✕":
      with self.subTest(glyph=glyph):
        self.assertEqual(terminal.display_width(glyph), 1)


  def test_repeated_current_refresh_has_identical_csv_and_lifecycle(self):
    # G15: unchanged authority must not create lifecycle history or drift.
    self.seed_all_states()
    lifecycle = LifecycleStore(self.root)
    before = {issue: lifecycle.read(issue) for issue in range(1, 7)}
    first = self.relationships.refresh_states(self.writer)
    original = self.relationships.path.read_bytes()
    second = self.relationships.refresh_states(self.writer)
    self.assertEqual(self.relationships.path.read_bytes(), original)
    self.assertEqual(first.states, second.states)
    self.assertEqual(first.revision, second.revision)
    self.assertEqual(
      {issue: lifecycle.read(issue) for issue in range(1, 7)},
      before,
    )

  def test_current_cli_failure_has_no_graph_output_or_partial_csv(self):
    # G07: CLI path as well as store path must fail closed.
    self.seed_all_states()
    original = self.relationships.path.read_bytes()
    words = ["lanes", "view", "--current"]
    output = StringIO()
    with patch(
      "repo_workflow.public_cli.runtime_writer_identity",
      return_value=self.writer,
    ):
      with patch(
        "repo_workflow.relationship_store.LifecycleStore.read",
        side_effect=RuntimeError("authoritative lifecycle unavailable"),
      ):
        with redirect_stdout(output):
          with self.assertRaisesRegex(
            RuntimeError, "authoritative lifecycle unavailable",
          ):
            _handle_lanes(
              self.root, words, LaneDiagnostics(self.root, tuple(words)),
            )
    self.assertEqual(output.getvalue(), "")
    self.assertEqual(self.relationships.path.read_bytes(), original)



  def test_legend_current_debug_and_lane_filter_preserve_lifecycle(self):
    # G11: joined public flags render graph first and keep lifecycle immutable.
    self.seed_all_states()
    lifecycle = LifecycleStore(self.root)
    before = {issue: lifecycle.read(issue) for issue in range(1, 7)}
    words = ["lanes", "view", "A", "--current", "--legend", "--debug"]
    parse_tokens(COMMANDS, Context(self.root, legal_only=False), words)
    output = StringIO()
    with patch(
      "repo_workflow.public_cli.runtime_writer_identity",
      return_value=self.writer,
    ):
      with redirect_stdout(output):
        _handle_lanes(
          self.root, words, LaneDiagnostics(self.root, tuple(words)),
        )
    result = output.getvalue()
    for glyph in "○●◎✓♥✕":
      self.assertIn(glyph, result)
    self.assertIn("Legend: ○ not_started", result)
    self.assertGreater(result.index("Legend:"), result.index("♥"))
    self.assertEqual(
      {issue: lifecycle.read(issue) for issue in range(1, 7)},
      before,
    )
    self.assertEqual(
      self.relationships.read().states["5"].state, "completed",
    )



if __name__ == "__main__":
  unittest.main()
