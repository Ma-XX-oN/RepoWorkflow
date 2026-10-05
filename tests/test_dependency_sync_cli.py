from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from repo_workflow.dependency_comparison import compare_dependencies
from repo_workflow.dependency_sync import DependencySyncResult, DependencySyncStatus
from repo_workflow.dependency_sync_cli import dependency_sync_command

class DependencySyncCliTests(unittest.TestCase):
  def current(self, selected="64"):
    value=Mock(); value.selected_issue=selected
    snap=Mock(); snap.value=value
    return snap

  @patch("repo_workflow.dependency_sync_cli.read_ticket_dependencies", return_value=(9,54))
  @patch("repo_workflow.dependency_sync_cli.RelationshipStore")
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.CurrentWorkStore")
  def test_compare_is_read_only(self,current,config,store,read):
    current.return_value.read.return_value=self.current()
    store.return_value.direct_dependencies.return_value=("2","9")
    with patch("repo_workflow.dependency_sync_cli.runtime_writer_identity") as writer:
      self.assertEqual(dependency_sync_command(Path("."),("dependency","to-tickets","--compare")),0)
      writer.assert_not_called()

  @patch("repo_workflow.dependency_sync_cli.refresh_issue_metadata")
  @patch("repo_workflow.dependency_sync_cli.sync_to_tickets")
  @patch("repo_workflow.dependency_sync_cli.runtime_writer_identity")
  @patch("repo_workflow.dependency_sync_cli.load_config", return_value={})
  @patch("repo_workflow.dependency_sync_cli.CurrentWorkStore")
  def test_mutation_refreshes_metadata(self,current,config,writer,sync,refresh):
    current.return_value.read.return_value=self.current()
    sync.return_value=DependencySyncResult(64,DependencySyncStatus.SYNCHRONIZED,compare_dependencies((2,),()),(2,))
    dependency_sync_command(Path("."),("dependency","to-tickets"))
    refresh.assert_called_once()

  @patch("repo_workflow.dependency_sync_cli.CurrentWorkStore")
  def test_missing_target_fails(self,current):
    current.return_value.read.return_value=self.current(None)
    with self.assertRaisesRegex(ValueError,"requires one selected issue"):
      dependency_sync_command(Path("."),("dependency","to-tickets"))

if __name__ == "__main__":
  unittest.main()
