from contextlib import redirect_stdout
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
      snapshot = store.transition(issue, transition, snapshot.revision)
    return snapshot

  def seed_all_states(self):
    self.advance(2, ("start",))
    self.advance(3, ("start", "submit-review"))
    self.advance(4, ("start", "submit-review", "accept"))
    self.advance(5, ("start", "submit-review", "accept", "complete"))
    self.advance(6, ("start", "abort"))

  def test_graph_reads_each_csv_state_immediately_without_refresh(self):
    self.seed_all_states()
    before = self.relationships.path.read_bytes()
    rendered = "\n".join(render_lanes(self.root))
    for glyph in "○●◎✓♥✕":
      self.assertIn(glyph, rendered)
    self.assertEqual(self.relationships.path.read_bytes(), before)
    self.assertFalse(list((self.root / ".repoworkflow/state/issues").glob("*/lifecycle.json")))

  def test_current_and_ordinary_views_read_the_same_csv(self):
    self.seed_all_states()
    before = self.relationships.path.read_bytes()
    outputs = []
    for words in (["lanes", "view"], ["lanes", "view", "--current"]):
      stream = StringIO()
      with redirect_stdout(stream):
        self.assertEqual(_handle_lanes(self.root, words, LaneDiagnostics(self.root, tuple(words))), 0)
      outputs.append(stream.getvalue())
    self.assertEqual(outputs[0], outputs[1])
    self.assertEqual(self.relationships.path.read_bytes(), before)








  def test_two_csv_writers_race_same_revision_one_wins(self):
    # P10: two concurrent state/graph CSV writes obey content CAS.
    original = self.relationships.read()
    barrier = Barrier(2)

    def replace(title):
      issues = dict(original.graph.issues)
      relation = issues["1"]
      issues["1"] = IssueRelationships(title, relation.depends_on)
      replacement = RelationshipGraph(issues=issues)
      barrier.wait(timeout=5)
      try:
        return self.relationships.replace(
          original.revision, replacement, self.writer,
        )
      except RelationshipStoreError as error:
        return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
      results = list(pool.map(replace, ("Writer A", "Writer B")))
    winners = [item for item in results if not isinstance(item, str)]
    losers = [item for item in results if isinstance(item, str)]
    self.assertEqual(len(winners), 1)
    self.assertEqual(len(losers), 1)
    self.assertIn("stale ticket-state revision", losers[0])
    self.assertEqual(RelationshipStore(self.root).read(), winners[0])
    self.assertIn(
      winners[0].graph.issues["1"].title, ("Writer A", "Writer B"),
    )

  def test_symbols_use_one_terminal_cell(self):
    terminal = TerminalStyler("never")
    for glyph in "○●◎✓♥✕":
      with self.subTest(glyph=glyph):
        self.assertEqual(terminal.display_width(glyph), 1)










if __name__ == "__main__":
  unittest.main()
