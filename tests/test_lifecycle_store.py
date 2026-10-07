from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.lifecycle_store import (
  IssueLifecycle,
  LifecycleError,
  LifecycleStore,
)
from repo_workflow.state_store import WriterIdentity


class LifecycleStoreTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=self.repo,
      check=True,
    )
    subprocess.run(
      ["git", "config", "user.name", "RWF Test"],
      cwd=self.repo,
      check=True,
    )
    self.store = LifecycleStore(self.repo)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def transition(
    self,
    issue,
    name,
    revision,
    candidate="v0.1.0-issue.1.0.0",
    relationship_revision=0,
  ):
    return self.store.transition(
      issue,
      name,
      candidate,
      relationship_revision,
      self.writer,
      revision,
    )

  def test_never_started_issue_projects_unstarted_without_record(self):
    snapshot = self.store.read(1)

    self.assertEqual(snapshot.lifecycle, IssueLifecycle.unstarted("1"))
    self.assertIsNone(snapshot.revision)
    self.assertFalse(
      (self.repo / ".repoworkflow/state/issues/1/lifecycle.json").exists()
    )

  def test_start_creates_revision_zero_and_normalized_active_state(self):
    snapshot = self.transition(1, "start", None)

    self.assertEqual(snapshot.revision, 0)
    self.assertEqual(snapshot.lifecycle.state, "active")
    self.assertFalse(snapshot.lifecycle.dependency_satisfied)
    self.assertEqual(snapshot.lifecycle.relationship_revision, 0)
    self.assertEqual(snapshot.lifecycle.history[0].from_state, "unstarted")
    self.assertEqual(snapshot.lifecycle.history[0].to_state, "active")

  def test_legal_lifecycle_round_trip_preserves_append_only_history(self):
    snapshot = self.transition(1, "start", None)
    snapshot = self.transition(1, "abort", snapshot.revision)
    snapshot = self.transition(1, "re-enter", snapshot.revision)
    snapshot = self.transition(1, "accept", snapshot.revision)
    snapshot = self.transition(1, "reject/reopen", snapshot.revision)
    snapshot = self.transition(1, "accept", snapshot.revision)
    snapshot = self.transition(1, "complete", snapshot.revision)

    reread = self.store.read(1)
    self.assertEqual(reread, snapshot)
    self.assertEqual(snapshot.lifecycle.state, "completed")
    self.assertTrue(snapshot.lifecycle.dependency_satisfied)
    self.assertEqual(
      [event.sequence for event in snapshot.lifecycle.history],
      list(range(7)),
    )

  def test_accepted_does_not_satisfy_dependency(self):
    snapshot = self.transition(1, "start", None)
    snapshot = self.transition(1, "accept", snapshot.revision)

    self.assertEqual(snapshot.lifecycle.state, "accepted")
    self.assertFalse(snapshot.lifecycle.dependency_satisfied)

  def test_illegal_transition_fails_without_mutation(self):
    snapshot = self.transition(1, "start", None)

    with self.assertRaisesRegex(LifecycleError, "illegal lifecycle transition"):
      self.transition(1, "complete", snapshot.revision)

    self.assertEqual(self.store.read(1), snapshot)

  def test_stale_revision_fails_without_mutation(self):
    snapshot = self.transition(1, "start", None)
    current = self.transition(1, "abort", snapshot.revision)

    with self.assertRaisesRegex(LifecycleError, "stale lifecycle revision"):
      self.transition(1, "re-enter", snapshot.revision)

    self.assertEqual(self.store.read(1), current)

  def test_malformed_value_fails_closed(self):
    path = self.repo / ".repoworkflow/state/issues/1/lifecycle.json"
    path.parent.mkdir(parents=True)
    path.write_text(
      '{"schema_version": 1, "key": "issues/1/lifecycle", '
      '"revision": 0, "previous_revision": null, '
      '"writer_id": "agent", "session_id": "session", '
      '"value": {"schema_version": 99}}\n',
      encoding="utf-8",
    )

    with self.assertRaises(LifecycleError):
      self.store.read(1)

  def test_missing_previously_committed_record_fails_closed(self):
    snapshot = self.transition(1, "start", None)
    self.assertEqual(snapshot.revision, 0)
    subprocess.run(["git", "add", ".repoworkflow"], cwd=self.repo, check=True)
    subprocess.run(
      ["git", "commit", "-m", "record lifecycle"],
      cwd=self.repo,
      check=True,
      capture_output=True,
    )
    path = self.repo / ".repoworkflow/state/issues/1/lifecycle.json"
    path.unlink()

    with self.assertRaisesRegex(
      LifecycleError,
      "missing but exists in repository history",
    ):
      self.store.read(1)

  def test_invalid_dependency_satisfaction_is_rejected(self):
    value = {
      "schema_version": 1,
      "issue": "1",
      "state": "accepted",
      "dependency_satisfied": True,
      "relationship_revision": 0,
      "history": [
        {
          "sequence": 0,
          "transition": "start",
          "from": "unstarted",
          "to": "active",
          "candidate": "candidate",
        },
        {
          "sequence": 1,
          "transition": "accept",
          "from": "active",
          "to": "accepted",
          "candidate": "candidate",
        },
      ],
    }

    with self.assertRaisesRegex(LifecycleError, "true exactly for completed"):
      IssueLifecycle.from_json_value(value)

  def test_schema_one_reads_with_empty_high_risk_aliases(self):
    value = {
      "schema_version": 1,
      "issue": "1",
      "state": "unstarted",
      "dependency_satisfied": False,
      "relationship_revision": None,
      "history": [],
    }
    lifecycle = IssueLifecycle.from_json_value(value)
    self.assertEqual(lifecycle.high_risk_aliases, ())
    self.assertEqual(lifecycle.schema_version, 2)

  def test_high_risk_aliases_round_trip_with_lifecycle(self):
    started = self.transition(1, "start", None)
    updated = self.store.set_high_risk_aliases(
      1,
      ["graph-renderer", "command-grammar", "graph-renderer"],
      self.writer,
      started.revision,
    )
    self.assertEqual(
      updated.lifecycle.high_risk_aliases,
      ("command-grammar", "graph-renderer"),
    )
    self.assertEqual(updated.lifecycle.state, "active")
    self.assertEqual(updated.lifecycle.history, started.lifecycle.history)
    self.assertEqual(self.store.read(1), updated)

  def test_lifecycle_transition_preserves_high_risk_aliases(self):
    started = self.transition(1, "start", None)
    tagged = self.store.set_high_risk_aliases(
      1,
      ["command-grammar"],
      self.writer,
      started.revision,
    )
    accepted = self.transition(1, "accept", tagged.revision)
    self.assertEqual(accepted.lifecycle.high_risk_aliases, ("command-grammar",))

  def test_high_risk_alias_replacement_is_deterministic(self):
    started = self.transition(1, "start", None)
    first = self.store.set_high_risk_aliases(
      1,
      ["b", "a"],
      self.writer,
      started.revision,
    )
    second = self.store.set_high_risk_aliases(
      1,
      ["a", "b", "a"],
      self.writer,
      first.revision,
    )
    self.assertEqual(first.lifecycle.high_risk_aliases, ("a", "b"))
    self.assertEqual(second.lifecycle.high_risk_aliases, ("a", "b"))

  def test_stale_high_risk_alias_write_fails_without_mutation(self):
    started = self.transition(1, "start", None)
    current = self.store.set_high_risk_aliases(
      1,
      ["a"],
      self.writer,
      started.revision,
    )
    with self.assertRaisesRegex(LifecycleError, "stale lifecycle revision"):
      self.store.set_high_risk_aliases(
        1,
        ["b"],
        self.writer,
        started.revision,
      )
    self.assertEqual(self.store.read(1), current)

  def test_invalid_high_risk_aliases_fail_closed(self):
    started = self.transition(1, "start", None)
    for aliases in ([""], [" bad"], [1], "alias"):
      with self.subTest(aliases=aliases):
        with self.assertRaises(LifecycleError):
          self.store.set_high_risk_aliases(
            1,
            aliases,
            self.writer,
            started.revision,
          )

  def test_issue_ids_are_canonical(self):
    for issue in (0, "0", "01", -1, True):
      with self.subTest(issue=issue):
        with self.assertRaises(LifecycleError):
          self.store.read(issue)


if __name__ == "__main__":
  unittest.main()
