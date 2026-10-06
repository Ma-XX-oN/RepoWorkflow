from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.dependency_sync import (
  DependencySyncConflict,
  DependencySyncStatus,
  sync_to_tickets,
)
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(title="Issue", *dependencies: int) -> IssueRelationships:
  return IssueRelationships(
    title,
    tuple(str(value) for value in dependencies),
  )


class ToTicketDependencySyncTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "2": relation("Two"),
        "9": relation("Nine"),
        "64": relation("Feature: Sixty Four", 2, 9),
      }),
      WriterIdentity("agent", "session"),
    )

  def tearDown(self):
    self.temp.cleanup()

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  @patch("repo_workflow.dependency_sync.resolve_dependency_config", return_value={})
  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  def test_empty_destination_is_synchronized(self, replace, _config, read):
    read.side_effect = [
      ("Feature: Sixty Four", ()),
      ("Feature: Sixty Four", (2, 9)),
    ]
    replace.return_value = (2, 9)
    result = sync_to_tickets(self.root, {}, 64)
    self.assertEqual(result.status, DependencySyncStatus.SYNCHRONIZED)

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  def test_identical_destination_is_idempotent(self, replace, read):
    read.return_value = ("Feature: Sixty Four", (2, 9))
    result = sync_to_tickets(self.root, {}, 64)
    self.assertEqual(result.status, DependencySyncStatus.MATCH)
    replace.assert_not_called()

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  def test_title_mismatch_blocks_before_dependency_mutation(self, replace, read):
    read.return_value = ("Server renamed", (2, 9))
    with self.assertRaisesRegex(DependencySyncConflict, "title conflict"):
      sync_to_tickets(self.root, {}, 64, replace=True)
    replace.assert_not_called()

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  @patch("repo_workflow.dependency_sync.replace_ticket_dependencies")
  def test_dependency_conflict_fails_without_replace(self, replace, read):
    read.return_value = ("Feature: Sixty Four", (9,))
    with self.assertRaisesRegex(DependencySyncConflict, "dependencies conflict"):
      sync_to_tickets(self.root, {}, 64)
    replace.assert_not_called()

  @patch("repo_workflow.dependency_sync.read_ticket_sync_state")
  def test_provider_failure_propagates(self, read):
    read.side_effect = RuntimeError("provider failed")
    with self.assertRaisesRegex(RuntimeError, "provider failed"):
      sync_to_tickets(self.root, {}, 64)


if __name__ == "__main__":
  unittest.main()
