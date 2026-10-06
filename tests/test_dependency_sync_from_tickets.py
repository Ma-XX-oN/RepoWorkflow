from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.dependency_sync import (
  DependencySyncConflict,
  DependencySyncStatus,
  sync_from_tickets,
)
from repo_workflow.relationship_registration import RelationshipRegistrationError
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(title="Issue", *dependencies: int) -> IssueRelationships:
  return IssueRelationships(
    title,
    tuple(str(value) for value in dependencies),
  )


class FromTicketDependencySyncTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "2": relation("Two"),
        "9": relation("Nine"),
        "54": relation("Fifty Four"),
        "64": relation("Old title"),
      }),
      self.writer,
    )

  def tearDown(self):
    self.temp.cleanup()

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_empty_destination_imports_title_and_dependencies(self, read):
    read.return_value = ("Server title", (2, 9))
    result = sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(result.status, DependencySyncStatus.SYNCHRONIZED)
    actual = RelationshipStore(self.root).issue(64)
    self.assertEqual(actual.title, "Server title")
    self.assertEqual(actual.depends_on, ("2", "9"))

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_identical_destination_is_idempotent(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation("Server title", 2, 9),
      }),
      self.writer,
    )
    prior = store.read()
    read.return_value = ("Server title", (2, 9))
    result = sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(result.status, DependencySyncStatus.MATCH)
    self.assertEqual(store.read(), prior)

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_dependency_conflict_fails_closed_without_replace(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation("Old title", 9),
      }),
      self.writer,
    )
    prior = store.read()
    read.return_value = ("Server title", (2, 9))
    with self.assertRaisesRegex(DependencySyncConflict, "dependencies conflict"):
      sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(store.read(), prior)

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_replace_updates_title_and_dependencies(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation("Old title", 54),
      }),
      self.writer,
    )
    read.return_value = ("Server title", (2, 9))
    result = sync_from_tickets(
      self.root,
      {},
      64,
      self.writer,
      replace=True,
    )
    self.assertEqual(result.dependencies, (2, 9))
    actual = store.issue(64)
    self.assertEqual(actual.title, "Server title")
    self.assertEqual(actual.depends_on, ("2", "9"))

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_replace_title_preserves_conflicting_local_dependencies(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation("Old title", 54),
      }),
      self.writer,
    )
    read.return_value = ("Server title", (2, 9))
    result = sync_from_tickets(
      self.root,
      {},
      64,
      self.writer,
      replace_title=True,
    )
    self.assertEqual(result.status, DependencySyncStatus.PARTIAL)
    actual = store.issue(64)
    self.assertEqual(actual.title, "Server title")
    self.assertEqual(actual.depends_on, ("54",))

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_concurrent_graph_change_is_detected_by_registration_cas(self, read):
    store = RelationshipStore(self.root)

    def concurrent(*_args):
      snapshot = store.read()
      store.replace(
        snapshot.revision,
        RelationshipGraph(issues={
          **snapshot.graph.issues,
          "54": relation("Changed"),
        }),
        WriterIdentity("other", "session"),
      )
      return ("Server title", (2, 9))

    read.side_effect = concurrent
    with self.assertRaisesRegex(
      RelationshipRegistrationError,
      "stale ticket-state revision",
    ):
      sync_from_tickets(self.root, {}, 64, self.writer)


if __name__ == "__main__":
  unittest.main()
