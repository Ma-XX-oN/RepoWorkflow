"""Independent #583 merge-side schema and provider-title authority oracles."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationships import RelationshipSchemaError
from repo_workflow.state_store import WriterIdentity
from repo_workflow.ticket_merge import merge_ticket_csv, merge_files
from tests.support import RepoFixture


class CanonicalCsvMergeAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("verifier", "session")

  def tearDown(self):
    self.temp.cleanup()

  def test_provider_title_authority_does_not_mutate_lifecycle(self):
    # P12: provider title wins; lifecycle stays authoritative and unchanged.
    lifecycle = LifecycleStore(self.root)
    started = lifecycle.transition(
      10, "start", "candidate", 0, self.writer, None,
    )
    path = self.root / ".repoworkflow/state/issues/10/lifecycle.json"
    original_bytes = path.read_bytes()
    base = (
      "issue,title,dependencies,state,state_revision\n"
      "10,Old,,active,0\n"
    )
    ours = base.replace("Old", "Ours")
    theirs = base.replace("Old", "Theirs")
    with patch(
      "repo_workflow.ticket_merge.resolve_info_config",
      return_value={"fixture": "provider"},
    ), patch(
      "repo_workflow.ticket_merge.issue_info",
      return_value={"title": "Provider authoritative title"},
    ) as info:
      merged = merge_ticket_csv(self.root, base, ours, theirs)
    info.assert_called_once()
    self.assertEqual(
      merged,
      "issue,title,dependencies,state,state_revision\n"
      "10,Provider authoritative title,,active,0\n",
    )
    self.assertEqual(LifecycleStore(self.root).read(10), started)
    self.assertEqual(path.read_bytes(), original_bytes)

  def test_merge_rejects_malformed_remote_schemas_without_changing_ours(self):
    # P16: unsupported remote schema/revision/status never silently wins.
    base = (
      "issue,title,dependencies,state,state_revision\n"
      "10,Ten,,active,0\n"
    )
    ours = base.replace("Ten", "Ours")
    malformed = (
      "issue,title,dependencies,unknown,revision\n10,Ten,,active,0\n",
      "issue,title,dependencies,state,state_revision\n10,Ten,,forged,0\n",
      "issue,title,dependencies,state,state_revision\n10,Ten,,active,-1\n",
      "issue,title,dependencies,state,state_revision\n10,Ten,,active,01\n",
      "issue,title,dependencies,state,state_revision\n10,Ten,,active\n",
    )
    for text in malformed:
      with self.subTest(remote=text):
        base_path = self.root / "base.csv"
        ours_path = self.root / "ours.csv"
        theirs_path = self.root / "theirs.csv"
        base_path.write_text(base, encoding="utf-8")
        ours_path.write_text(ours, encoding="utf-8")
        theirs_path.write_text(text, encoding="utf-8")
        previous = ours_path.read_bytes()
        with self.assertRaises(RelationshipSchemaError):
          merge_files(self.root, base_path, ours_path, theirs_path)
        self.assertEqual(ours_path.read_bytes(), previous)


if __name__ == "__main__":
  unittest.main()
