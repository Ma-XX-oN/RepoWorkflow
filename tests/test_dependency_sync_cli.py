from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from repo_workflow.dependency_sync import DependencySyncConflict
from repo_workflow.dependency_sync_cli import dependency_sync_command
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def snapshot():
  value = Mock()
  value.revision = 7
  value.graph = RelationshipGraph(issues={
    "2": IssueRelationships("Two", ()),
    "9": IssueRelationships("Nine", ()),
    "64": IssueRelationships("Sixty Four", ("2", "9")),
    "65": IssueRelationships("Sixty Five", ()),
  })
  return value


class DependencySyncCliTests(unittest.TestCase):
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_compare_is_multi_issue_and_read_only(self, read, store, _config):
    store.return_value.read.return_value = snapshot()
    read.side_effect = [
      ("Sixty Four", (2, 9)),
      ("Sixty Five", ()),
    ]
    with patch(
      "repo_workflow.dependency_sync_cli.runtime_writer_identity"
    ) as writer:
      result = dependency_sync_command(
        Path("."),
        (
          "64",
          "65",
          "dependency",
          "to-tickets",
          "--compare",
        ),
      )
    self.assertEqual(result, 0)
    writer.assert_not_called()
    self.assertEqual(read.call_count, 2)

  def test_explicit_issue_list_is_required_and_validated(self):
    with self.assertRaisesRegex(ValueError, "invalid dependency"):
      dependency_sync_command(
        Path("."),
        ("dependency", "to-tickets"),
      )
    with self.assertRaisesRegex(ValueError, "duplicate issue"):
      dependency_sync_command(
        Path("."),
        ("64", "64", "dependency", "to-tickets"),
      )

  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  @patch("repo_workflow.dependency_sync_cli.replace_ticket_dependencies")
  def test_multi_issue_to_tickets_preflights_before_any_mutation(
    self,
    replace,
    read,
    store,
    _config,
  ):
    store.return_value.read.return_value = snapshot()
    read.side_effect = [
      ("Sixty Four", ()),
      ("Wrong server title", ()),
    ]
    with self.assertRaisesRegex(DependencySyncConflict, "title conflict"):
      dependency_sync_command(
        Path("."),
        ("64", "65", "dependency", "to-tickets"),
      )
    replace.assert_not_called()

  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_from_tickets_compare_reports_title_and_dependency_state(
    self,
    read,
    store,
    _config,
  ):
    store.return_value.read.return_value = snapshot()
    read.return_value = ("Renamed on server", (2,))
    self.assertEqual(
      dependency_sync_command(
        Path("."),
        ("64", "dependency", "from-tickets", "--compare"),
      ),
      0,
    )


if __name__ == "__main__":
  unittest.main()
