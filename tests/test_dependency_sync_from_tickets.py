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


def relation(*dependencies: int, parent: str | None = None) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(value) for value in dependencies))


class FromTicketDependencySyncTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "2": relation(),
        "9": relation(),
        "54": relation(),
        "64": relation(parent="main"),
      }),
      self.writer,
    )

  def tearDown(self):
    self.temp.cleanup()

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_empty_rwf_destination_imports_through_registration(self, read):
    read.return_value = (2, 9)
    result = sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(result.status, DependencySyncStatus.SYNCHRONIZED)
    relation64 = RelationshipStore(self.root).issue(64)
    self.assertEqual(relation64.depends_on, ("2", "9"))
    self.assertEqual(relation64.parent, "main")

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_identical_rwf_destination_is_idempotent(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation(2, 9, parent="main"),
      }),
      self.writer,
    )
    prior = store.read()
    read.return_value = (2, 9)
    result = sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(result.status, DependencySyncStatus.MATCH)
    self.assertEqual(store.read(), prior)

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_conflict_fails_closed(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation(9, parent="main"),
      }),
      self.writer,
    )
    prior = store.read()
    read.return_value = (2, 9)
    with self.assertRaisesRegex(DependencySyncConflict, "conflict"):
      sync_from_tickets(self.root, {}, 64, self.writer)
    self.assertEqual(store.read(), prior)

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_replace_changes_only_direct_dependencies(self, read):
    store = RelationshipStore(self.root)
    before = store.read()
    store.replace(
      before.revision,
      RelationshipGraph(issues={
        **before.graph.issues,
        "64": relation(54, parent="main"),
      }),
      self.writer,
    )
    read.return_value = (2, 9)
    result = sync_from_tickets(
      self.root, {}, 64, self.writer, replace=True
    )
    self.assertEqual(result.dependencies, (2, 9))
    self.assertEqual(RelationshipStore(self.root).issue(64).parent, "main")

  @patch("repo_workflow.dependency_sync.read_ticket_dependencies")
  def test_concurrent_graph_change_is_detected_by_registration_cas(self, read):
    store = RelationshipStore(self.root)

    def concurrent(*_args):
      snapshot = store.read()
      store.replace(
        snapshot.revision,
        RelationshipGraph(issues={
          **snapshot.graph.issues,
          "54": relation(parent="main"),
        }),
        WriterIdentity("other", "session"),
      )
      return (2, 9)

    read.side_effect = concurrent
    with self.assertRaisesRegex(
      RelationshipRegistrationError,
      "stale relationship graph revision",
    ):
      sync_from_tickets(self.root, {}, 64, self.writer)


if __name__ == "__main__":
  unittest.main()
