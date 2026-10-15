"""Independent malformed lifecycle history acceptance (#583 L16)."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from repo_workflow.lifecycle_store import (
  IssueLifecycle, LifecycleError, LifecycleStore,
)
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class LifecycleHistoryCorruptionAcceptance(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("verifier", "session")
    self.lifecycle = LifecycleStore(self.root)

  def tearDown(self):
    self.temp.cleanup()

  def test_truncated_conflicting_noncontiguous_and_forged_events_fail(self):
    snapshot = self.lifecycle.transition(
      1, "start", "candidate", 0, self.writer, None,
    )
    snapshot = self.lifecycle.transition(
      1, "submit-review", "candidate", 0,
      self.writer, snapshot.revision,
    )
    source = snapshot.lifecycle.to_json_value()
    self.assertEqual(IssueLifecycle.from_json_value(source), snapshot.lifecycle)
    path = self.root / ".repoworkflow" / "state" / "issues" / "1" / "lifecycle.json"
    before = path.read_bytes()

    fixtures = (
      lambda x: x["history"].pop(),
      lambda x: x["history"][0].update({"sequence": 4}),
      lambda x: x["history"][1].update({"from": "not_started"}),
      lambda x: x["history"][1].update({"to": "completed"}),
      lambda x: x["history"][1].update({"transition": "complete"}),
      lambda x: x.update({"legacy_event_count": 3}),
      lambda x: x.update({"legacy_event_count": -1}),
      lambda x: x.update({"state": "completed"}),
      lambda x: x.update({"history": "not an array"}),
    )
    for corrupt in fixtures:
      value = deepcopy(source)
      corrupt(value)
      with self.subTest(malformed=value):
        with self.assertRaises(LifecycleError):
          IssueLifecycle.from_json_value(value)
        self.assertEqual(self.lifecycle.read(1), snapshot)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
  unittest.main()
