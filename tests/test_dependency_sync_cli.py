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


  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity")
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_from_tickets_replace_title_preserves_local_dependencies(
    self,
    read,
    store,
    _config,
    writer,
  ):
    snap = snapshot()
    store.return_value.read.return_value = snap
    read.return_value = ("Renamed on server", (2,))
    writer.return_value = Mock()
    self.assertEqual(
      dependency_sync_command(
        Path("."),
        ("64", "dependency", "from-tickets", "--replace-title"),
      ),
      0,
    )
    replacement = store.return_value.replace.call_args.args[1]
    self.assertEqual(replacement.issue(64).title, "Renamed on server")
    self.assertEqual(replacement.issue(64).depends_on, ("2", "9"))

  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity")
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_from_tickets_replace_dependencies_also_accepts_server_title(
    self,
    read,
    store,
    _config,
    writer,
  ):
    snap = snapshot()
    store.return_value.read.return_value = snap
    read.return_value = ("Renamed on server", (2,))
    writer.return_value = Mock()
    self.assertEqual(
      dependency_sync_command(
        Path("."),
        ("64", "dependency", "from-tickets", "--replace-dependencies"),
      ),
      0,
    )
    replacement = store.return_value.replace.call_args.args[1]
    self.assertEqual(replacement.issue(64).title, "Renamed on server")
    self.assertEqual(replacement.issue(64).depends_on, ("2",))

  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity")
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_from_tickets_replace_updates_title_and_dependencies_atomically(
    self,
    read,
    store,
    _config,
    writer,
  ):
    snap = snapshot()
    store.return_value.read.return_value = snap
    read.side_effect = [
      ("Server 64", (2,)),
      ("Server 65", (9,)),
    ]
    writer.return_value = Mock()
    self.assertEqual(
      dependency_sync_command(
        Path("."),
        ("64", "65", "dependency", "from-tickets", "--replace"),
      ),
      0,
    )
    self.assertEqual(store.return_value.replace.call_count, 1)
    replacement = store.return_value.replace.call_args.args[1]
    self.assertEqual(replacement.issue(64).title, "Server 64")
    self.assertEqual(replacement.issue(64).depends_on, ("2",))
    self.assertEqual(replacement.issue(65).title, "Server 65")
    self.assertEqual(replacement.issue(65).depends_on, ("9",))

  @patch("repo_workflow.dependency_sync_cli.refresh_issue_metadata")
  @patch("repo_workflow.dependency_sync_cli.resolve_info_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity")
  @patch("repo_workflow.dependency_sync_cli.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync_cli.resolve_dependency_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_to_tickets_success_refreshes_metadata_after_verified_readback(
    self,
    read,
    store,
    _config,
    _dep_config,
    replace,
    writer,
    _info_config,
    refresh,
  ):
    store.return_value.read.return_value = snapshot()
    read.side_effect = [
      ("Sixty Four", ()),
      ("Sixty Four", (2, 9)),
    ]
    replace.return_value = (2, 9)
    writer.return_value = Mock()
    self.assertEqual(
      dependency_sync_command(
        Path("."),
        ("64", "dependency", "to-tickets"),
      ),
      0,
    )
    replace.assert_called_once()
    refresh.assert_called_once()

  @patch("repo_workflow.dependency_sync_cli.replace_ticket_dependencies")
  @patch("repo_workflow.dependency_sync_cli.resolve_dependency_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.read_ticket_sync_state")
  def test_to_tickets_rolls_back_earlier_issue_when_later_mutation_fails(
    self,
    read,
    store,
    _config,
    _dep_config,
    replace,
  ):
    store.return_value.read.return_value = snapshot()
    read.side_effect = [
      ("Sixty Four", ()),
      ("Sixty Five", (9,)),
      ("Sixty Four", (2, 9)),
    ]
    replace.side_effect = [
      (2, 9),
      RuntimeError("provider mutation failed"),
      (),
    ]
    with self.assertRaisesRegex(RuntimeError, "provider mutation failed"):
      dependency_sync_command(
        Path("."),
        ("64", "65", "dependency", "to-tickets", "--replace"),
      )
    self.assertEqual(replace.call_count, 3)
    self.assertEqual(replace.call_args_list[-1].args[3], ())



if __name__ == "__main__":
  unittest.main()
