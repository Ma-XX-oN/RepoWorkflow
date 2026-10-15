"""Black-box #583 strict CSV and offline graph acceptance probes."""

from pathlib import Path
import socket
from contextlib import redirect_stdout
from io import StringIO
import urllib.request
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.relationship_store import (
  RelationshipStore, RelationshipStoreError,
)
from repo_workflow.relationships import IssueRelationships, RelationshipGraph, ready_issues
from repo_workflow.state_store import WriterIdentity
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.lane_render import render_lanes
from repo_workflow.current_work_store import CurrentWorkStore
from repo_workflow.public_cli import _handle_lanes
from repo_workflow.lane_diagnostics import LaneDiagnostics
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from tests.support import RepoFixture


class StrictCsvAndOfflineAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("verifier", "session")
    self.store = RelationshipStore(self.root)
    self.store.create(RelationshipGraph(issues={
      "1": IssueRelationships("One", ()),
      "2": IssueRelationships("Two", ("1",)),
    }), self.writer)

  def tearDown(self):
    self.temp.cleanup()

  def test_duplicate_unknown_cycle_and_invalid_identifier_fail_closed(self):
    # P18: malformed CSV never silently rewrites a canonical graph.
    baseline = self.store.path.read_bytes()
    fixtures = (
      "issue,title,dependencies\n1,One,\n1,Duplicate,\n",
      "issue,title,dependencies\n1,One,\n2,Two,999\n",
      "issue,title,dependencies\n1,One,2\n2,Two,1\n",
      "issue,title,dependencies\n0,Zero,\n",
      "issue,title,dependencies\n01,Leading,\n",
      "issue,title,dependencies\n2,Two,\n1,One,\n",
      "issue,title,dependencies\n1,One,1\n",
    )
    for bad in fixtures:
      with self.subTest(bad=bad):
        self.store.path.write_text(bad, encoding="utf-8")
        original = self.store.path.read_bytes()
        with self.assertRaises(RelationshipStoreError):
          self.store.read()
        self.assertEqual(self.store.path.read_bytes(), original)
    self.store.path.write_bytes(baseline)
    self.assertEqual(RelationshipStore(self.root).read(), self.store.read())

  def test_provider_title_refresh_cannot_rewrite_lifecycle_projection(self):
    # P12: graph title edit preserves the source-of-truth lifecycle.
    lifecycle = LifecycleStore(self.root)
    begun = lifecycle.transition(
      1, "start", "candidate", 0, self.writer, None,
    )
    refreshed = self.store.refresh_states(self.writer)
    changed = RelationshipGraph(issues={
      "1": IssueRelationships("Authoritative new title", ()),
      "2": IssueRelationships("Two", ("1",)),
    })
    revised = self.store.replace(refreshed.revision, changed, self.writer)
    self.assertEqual(revised.states, refreshed.states)
    self.assertEqual(lifecycle.read(1), begun)
    self.assertEqual(RelationshipStore(self.root).read(), revised)

  def test_graph_ignores_different_current_worktree_issue(self):
    # G14: worktree navigation pointer is not the graph-state authority.
    lifecycle = LifecycleStore(self.root)
    active = lifecycle.transition(
      1, "start", "candidate-1", 0, self.writer, None,
    )
    completed = lifecycle.transition(
      2, "start", "candidate-2", 0, self.writer, None,
    )
    for action in ("submit-review", "accept", "complete"):
      completed = lifecycle.transition(
        2, action, "candidate-2", 0, self.writer, completed.revision,
      )
    refreshed = self.store.refresh_states(self.writer)
    pointer = CurrentWorkStore(self.root).project_start(
      1, active.revision, refreshed.revision, self.writer, None,
    )
    self.assertEqual(pointer.value.current.issue, "1")
    self.assertEqual(refreshed.states["2"].state, "completed")
    LaneSelectionStore(self.root).select((2,), self.writer)
    IssueMetadataStore(self.root).write({
      issue: IssueMetadata(
        number=issue, title=f"Ticket {issue}", state="open",
        link=f"https://example.invalid/{issue}",
      )
      for issue in (1, 2)
    }, self.writer)
    before = self.store.path.read_bytes()
    with patch.object(
      CurrentWorkStore, "read",
      side_effect=AssertionError("graph consumed worktree pointer"),
    ):
      graph = "\n".join(render_lanes(self.root))
    self.assertIn("●", graph)
    self.assertIn("♥", graph)
    self.assertEqual(self.store.path.read_bytes(), before)
    self.assertEqual(CurrentWorkStore(self.root).read(), pointer)

  def test_same_active_state_preserves_distinct_dependency_readiness(self):
    # G04: readiness is derived from dependencies, never lifecycle glyph.
    lifecycle = LifecycleStore(self.root)
    for issue in (1, 2):
      lifecycle.transition(
        issue, "start", f"candidate-{issue}", 0, self.writer, None,
      )
    refreshed = self.store.refresh_states(self.writer)
    self.assertEqual(
      (refreshed.states["1"].state, refreshed.states["2"].state),
      ("active", "active"),
    )
    self.assertEqual(ready_issues(refreshed.graph, set()), ("1",))
    self.assertEqual(ready_issues(refreshed.graph, {"1"}), ("2",))
    LaneSelectionStore(self.root).select((2,), self.writer)
    IssueMetadataStore(self.root).write({
      issue: IssueMetadata(
        number=issue, title=f"Ticket {issue}", state="open",
        link=f"https://example.invalid/{issue}",
      )
      for issue in (1, 2)
    }, self.writer)
    before = self.store.path.read_bytes()
    rendered = "\n".join(render_lanes(self.root))
    self.assertGreaterEqual(rendered.count("●"), 2)
    self.assertEqual(self.store.path.read_bytes(), before)

  def test_mixed_lifecycle_sample_changed_during_refresh_is_rejected(self):
    # P06: changes to earlier issues during later sampling fail atomically.
    lifecycle = LifecycleStore(self.root)
    first = lifecycle.transition(
      1, "start", "candidate-1", 0, self.writer, None,
    )
    lifecycle.transition(2, "start", "candidate-2", 0, self.writer, None)
    previous = self.store.path.read_bytes()
    original_read = LifecycleStore.read
    injected = False

    def interleaved_read(reader, issue):
      nonlocal injected
      value = original_read(reader, issue)
      if str(issue) == "2" and not injected:
        injected = True
        lifecycle.transition(
          1, "submit-review", "candidate-1", 0,
          self.writer, first.revision,
        )
      return value

    with patch(
      "repo_workflow.relationship_store.LifecycleStore.read",
      new=interleaved_read,
    ):
      with self.assertRaisesRegex(
        RelationshipStoreError, "stale lifecycle projection",
      ):
        self.store.refresh_states(self.writer)
    self.assertTrue(injected)
    self.assertEqual(self.store.path.read_bytes(), previous)
    refreshed = self.store.refresh_states(self.writer)
    self.assertEqual(refreshed.states["1"].state, "in_review")
    self.assertEqual(refreshed.states["1"].lifecycle_revision, 1)
    self.assertEqual(refreshed.states["2"].state, "active")
    self.assertEqual(refreshed.states["2"].lifecycle_revision, 0)
    self.assertEqual(RelationshipStore(self.root).read(), refreshed)

  def test_default_graph_is_offline_and_never_refreshes_lifecycle(self):
    # G01: cached graph must never consult lifecycle or a remote provider.
    LaneSelectionStore(self.root).select((2,), self.writer)
    IssueMetadataStore(self.root).write({
      issue: IssueMetadata(
        number=issue, title=f"Ticket {issue}", state="open",
        link=f"https://example.invalid/{issue}",
      )
      for issue in (1, 2)
    }, self.writer)
    csv_before = self.store.path.read_bytes()
    with patch(
      "repo_workflow.lifecycle_store.LifecycleStore.read",
      side_effect=AssertionError("default graph polled lifecycle"),
    ), patch.object(
      socket, "create_connection",
      side_effect=AssertionError("default graph opened network"),
    ), patch.object(
      urllib.request, "urlopen",
      side_effect=AssertionError("default graph opened network"),
    ):
      lines = render_lanes(self.root)
    self.assertTrue(lines)
    self.assertEqual(self.store.path.read_bytes(), csv_before)
    self.assertIsNone(RelationshipStore(self.root).read().states)

  def test_public_current_unavailable_authority_has_no_partial_output(self):
    # G06: public --current requires authoritative refresh, never fallback.
    LaneSelectionStore(self.root).select((2,), self.writer)
    IssueMetadataStore(self.root).write({
      issue: IssueMetadata(
        number=issue, title=f"Ticket {issue}", state="closed",
        link=f"https://example.invalid/{issue}",
      )
      for issue in (1, 2)
    }, self.writer)
    before = self.store.path.read_bytes()
    output = StringIO()
    words = ["lanes", "view", "--current"]
    with patch(
      "repo_workflow.public_cli.runtime_writer_identity",
      return_value=self.writer,
    ), patch(
      "repo_workflow.relationship_store.LifecycleStore.read",
      side_effect=OSError("provider authority unavailable"),
    ), redirect_stdout(output):
      with self.assertRaisesRegex(OSError, "authority unavailable"):
        _handle_lanes(
          self.root, words, LaneDiagnostics(self.root, tuple(words)),
        )
    self.assertEqual(output.getvalue(), "")
    self.assertEqual(self.store.path.read_bytes(), before)

  def test_explicit_refresh_unavailable_authority_preserves_csv(self):
    # G06: explicit current cannot fabricate state on unavailable authority.
    before = self.store.path.read_bytes()
    with patch(
      "repo_workflow.relationship_store.LifecycleStore.read",
      side_effect=OSError("authoritative lifecycle unavailable"),
    ):
      with self.assertRaisesRegex(OSError, "unavailable"):
        self.store.refresh_states(self.writer)
    self.assertEqual(self.store.path.read_bytes(), before)


if __name__ == "__main__":
  unittest.main()
