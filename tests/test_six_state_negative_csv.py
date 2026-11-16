"""Black-box #583 strict CSV and offline graph acceptance probes."""

from pathlib import Path
import socket
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import StringIO
import urllib.request
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.relationship_store import (
  RelationshipStore, RelationshipStoreError,
)
from repo_workflow.relationships import IssueRelationships, RelationshipGraph, ready_issues
from repo_workflow.state_store import WriterIdentity
from repo_workflow.lifecycle_store import LifecycleStore, LifecycleError
from repo_workflow.lane_render import render_lanes
from repo_workflow.current_work_store import CurrentWorkStore, CurrentWorkError
from repo_workflow.public_cli import _handle_lanes
from repo_workflow.lane_diagnostics import LaneDiagnostics
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
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















if __name__ == "__main__":
  unittest.main()
