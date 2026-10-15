"""Black-box #583 strict CSV and offline graph acceptance probes."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.relationship_store import (
  RelationshipStore, RelationshipStoreError,
)
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from repo_workflow.lifecycle_store import LifecycleStore
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
