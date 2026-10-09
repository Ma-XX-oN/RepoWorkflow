from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

from repo_workflow.ticket_merge import (
  TicketMergeError,
  configure_ticket_merge_driver,
  merge_ticket_csv,
)


def csv(*rows: str) -> str:
  return "issue,title,dependencies\n" + "\n".join(rows) + "\n"


class TicketMergeTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()

  def tearDown(self):
    self.temp.cleanup()

  def test_configure_installs_local_git_driver(self):
    import subprocess
    subprocess.run(
      ["git", "init"],
      cwd=self.root,
      check=True,
      capture_output=True,
      text=True,
    )
    engine = Path(__file__).resolve().parents[1]
    configure_ticket_merge_driver(self.root, engine)
    name = subprocess.run(
      ["git", "config", "--local", "--get", "merge.rwf-tickets.name"],
      cwd=self.root,
      check=True,
      capture_output=True,
      text=True,
    ).stdout.strip()
    driver = subprocess.run(
      ["git", "config", "--local", "--get", "merge.rwf-tickets.driver"],
      cwd=self.root,
      check=True,
      capture_output=True,
      text=True,
    ).stdout.strip()
    self.assertEqual(name, "RepoWorkflow synchronized ticket merge")
    self.assertIn("merge-ticket-state.py", driver)
    self.assertIn("%O", driver)
    self.assertIn("%A", driver)
    self.assertIn("%B", driver)

  def test_non_overlapping_changes_merge_without_provider(self):
    base = csv('10,"Ten",', '20,"Twenty",10')
    ours = csv('10,"Ten",', '20,"Twenty",')
    theirs = csv('10,"Ten",', '20,"Twenty renamed",10')
    with patch(
      "repo_workflow.ticket_merge.resolve_info_config",
      return_value={},
    ):
      with patch(
        "repo_workflow.ticket_merge.issue_info",
        return_value={"title": "Twenty renamed"},
      ):
        merged = merge_ticket_csv(self.root, base, ours, theirs)
    self.assertIn("20,Twenty renamed,", merged)

  def test_divergent_title_uses_provider_authority(self):
    base = csv('10,"Old",')
    ours = csv('10,"Ours",')
    theirs = csv('10,"Theirs",')
    with patch(
      "repo_workflow.ticket_merge.resolve_info_config",
      return_value={},
    ):
      with patch(
        "repo_workflow.ticket_merge.issue_info",
        return_value={"title": "Server"},
      ):
        merged = merge_ticket_csv(self.root, base, ours, theirs)
    self.assertIn("10,Server,", merged)
    self.assertNotIn("Ours", merged)
    self.assertNotIn("Theirs", merged)

  def test_title_conflict_provider_failure_fails_closed(self):
    base = csv('10,"Old",')
    ours = csv('10,"Ours",')
    theirs = csv('10,"Theirs",')
    with patch(
      "repo_workflow.ticket_merge.resolve_info_config",
      side_effect=RuntimeError("offline"),
    ):
      with self.assertRaisesRegex(
        TicketMergeError,
        "cannot resolve authoritative title",
      ):
        merge_ticket_csv(self.root, base, ours, theirs)

  def test_divergent_dependency_changes_conflict(self):
    base = csv('10,"Ten",', '20,"Twenty",10', '30,"Thirty",10')
    ours = csv('10,"Ten",', '20,"Twenty",10;30', '30,"Thirty",10')
    theirs = csv('10,"Ten",', '20,"Twenty",', '30,"Thirty",10')
    with self.assertRaisesRegex(
      TicketMergeError,
      "divergent dependency changes",
    ):
      merge_ticket_csv(self.root, base, ours, theirs)


  def test_status_snapshot_preserved_in_semantic_merge(self):
    base = (
      "issue,title,dependencies,state,state_revision\\n"
      "10,Ten,,not_started,\\n"
    )
    ours = (
      "issue,title,dependencies,state,state_revision\\n"
      "10,Ten,,active,0\\n"
    )
    theirs = base
    self.assertEqual(
      merge_ticket_csv(self.root, base, ours, theirs),
      ours,
    )

  def test_divergent_status_snapshots_conflict(self):
    base = (
      "issue,title,dependencies,state,state_revision\\n"
      "10,Ten,,not_started,\\n"
    )
    ours = (
      "issue,title,dependencies,state,state_revision\\n"
      "10,Ten,,active,0\\n"
    )
    theirs = (
      "issue,title,dependencies,state,state_revision\\n"
      "10,Ten,,completed,1\\n"
    )
    with self.assertRaisesRegex(TicketMergeError, "divergent lifecycle"):
      merge_ticket_csv(self.root, base, ours, theirs)

  def test_same_addition_is_idempotent(self):
    base = csv("10,Ten,")
    ours = csv("10,Ten,", "20,Twenty,10")
    theirs = ours
    self.assertEqual(
      merge_ticket_csv(self.root, base, ours, theirs),
      ours,
    )


if __name__ == "__main__":
  unittest.main()
