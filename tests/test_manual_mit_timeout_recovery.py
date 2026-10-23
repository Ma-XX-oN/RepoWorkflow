"""Independent #703 claimed-MIT timeout recovery contracts.

Unit fixtures only: these are not authenticated production-provider results.
Never replay claim_prelim after an externally committed lease-CAS ACK loss.
"""
import unittest

from repo_workflow.done_host_coordinator import IntegrationHostCoordinator
from repo_workflow.done_mit_defer_v2 import MitDeferError, defer_mit_with_provider
from repo_workflow.integration_coordination import (
  CoordinationError, DestinationLease, claim_prelim, release_prelim,
)
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_provider_pipeline import Provider, A, B, G, P


class LostAcknowledgementHost(Provider):
  """Write succeeded remotely before the client's ACK was lost."""

  def __init__(self):
    super().__init__()
    self.lose_deferred_ack = False
    self.lose_read = False
    self.publish_count = 0

  def request(self, operation, request_id, params):
    if operation == "mit.deferred.read" and self.lose_read:
      self.calls.append(operation)
      return {"guid": G, "destination": "main", "event": None}
    result = super().request(operation, request_id, params)
    if operation == "mit.deferred.record":
      self.publish_count += 1
      if self.lose_deferred_ack:
        raise ConnectionError("provider persisted event; response lost")
    return result


class ClaimedTimeoutRecoveryTests(unittest.TestCase):
  def setUp(self):
    self.host = LostAcknowledgementHost()
    self.ready = parse_ready_prelim(P, A)
    self.host.lease = {
      "destination": "main", "generation": 1,
      "guid": G, "holder": "worker-A",
    }
    self.claim = DestinationLease("main", 1, G, "worker-A")
    self.provider = IntegrationHostCoordinator(self.host)

  def defer(self):
    return defer_mit_with_provider(
      host=self.host, ready=self.ready, lease=self.claim,
      holder="worker-A", reason="timeout",
      evidence_ref="github-actions-real-timeout-job-124",
      event_request_id="rwf703-recovery-event-1",
      read_request_id="rwf703-recovery-independent-read-2",
    )

  def test_claimed_lease_resumed_without_second_claim(self):
    outcome = self.defer()
    self.assertEqual(outcome.released_generation, 2)
    self.assertEqual(self.host.lease["generation"], 2)
    self.assertIsNone(self.host.lease["guid"])
    self.assertIsNone(self.host.lease["holder"])
    self.assertEqual(self.host.deferred["reason"], "timeout")
    self.assertEqual(self.host.deferred["prelim_sha"], A)
    self.assertEqual(self.host.deferred["lease_generation"], 1)
    self.assertEqual(self.host.deferred["evidence_ref"],
                     "github-actions-real-timeout-job-124")
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.main, B)
    self.assertNotIn("destination.accept", self.host.calls)
    self.assertEqual(self.host.calls.count("lease.cas"), 1)

  def test_persisted_event_lost_ack_reconciles_without_double_append(self):
    self.host.lose_deferred_ack = True
    outcome = self.defer()
    self.assertEqual(outcome.released_generation, 2)
    self.assertEqual(self.host.publish_count, 1)
    self.assertEqual(self.host.deferred["reason"], "timeout")
    self.assertEqual(self.host.main, B)
    self.assertIsNone(self.host.terminal)

  def test_unknown_readback_retains_claim_then_read_only_recovers(self):
    self.host.lose_read = True
    with self.assertRaisesRegex(MitDeferError, "absent"):
      self.defer()
    self.assertEqual(self.host.publish_count, 1)
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertEqual(self.host.lease["holder"], "worker-A")
    self.assertIsNotNone(self.host.deferred)
    self.assertEqual(self.host.main, B)
    self.host.lose_read = False
    # The write was already durable; a second POST would be a bug.
    released = release_prelim(
      self.provider, self.claim, "worker-A",
      terminal_result="deferred-mit", submission=self.ready,
    )
    self.assertEqual(released.generation, 2)
    self.assertEqual(self.host.publish_count, 1)

  def test_deferred_attempt_denies_reclaim_without_exact_approval(self):
    self.defer()
    with self.assertRaisesRegex(CoordinationError, "approved"):
      claim_prelim(self.provider, self.ready, "worker-B")
    self.assertEqual(self.host.lease["generation"], 2)
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.main, B)

  def test_wrong_or_foreign_claim_fails_without_provider_mutation(self):
    other = DestinationLease("main", 1, G, "other-holder")
    with self.assertRaises(MitDeferError):
      defer_mit_with_provider(
        host=self.host, ready=self.ready, lease=other,
        holder="other-holder", reason="timeout",
        evidence_ref="real-artifact-124", event_request_id="x",
        read_request_id="y",
      )
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertIsNone(self.host.deferred)
    self.assertEqual(self.host.main, B)

  def test_terminal_failed_attempt_is_not_misclassified_as_timeout(self):
    self.host.terminal = {
      "guid": G, "repository": self.host.repository, "status": "failed"
    }
    with self.assertRaisesRegex(MitDeferError, "terminal"):
      self.defer()
    self.assertEqual(self.host.lease["generation"], 1)
    self.assertIsNone(self.host.deferred)
    self.assertEqual(self.host.main, B)


class NativeVersionAndLifecycleFailureTests(unittest.TestCase):
  """Real local Git/lifecycle/version adapters, not remote provider proof."""

  def test_manual_fail_real_git_reopens_and_increments_q_resets_r(self):
    import json
    from pathlib import Path
    import subprocess
    import tempfile
    from types import SimpleNamespace

    from repo_workflow.lifecycle_store import LifecycleStore
    from repo_workflow.manual_test_result import (
      record_manual_result, read_manual_case_results,
    )
    from repo_workflow.manual_test_state import select_manual_case
    from repo_workflow.state_store import WriterIdentity
    from tests.support import RepoFixture
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "repo"
      root.mkdir()
      fixture = RepoFixture(root, version="1.0.0-issue.703.5.7")
      candidate = fixture.head()
      destination_before = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "refs/heads/main"],
        text=True,
      ).strip()
      writer = WriterIdentity("certifier-703", "independent-native-failure")
      store = LifecycleStore(root)
      started = store.transition(703, "start", None, None, writer, None)
      review = store.transition(
        703, "submit-review", candidate, None, writer, started.revision,
      )
      accepted = store.transition(
        703, "accept", candidate, None, writer, review.revision,
      )
      self.assertEqual(accepted.lifecycle.state, "accepted")
      self.assertFalse(accepted.lifecycle.dependency_satisfied)
      case = SimpleNamespace(
        name="issue-703-manual--NEGATIVE",
        definition_digest="a" * 64,
      )
      selected = select_manual_case(root, 703, candidate, case, cases=(case,))
      self.assertEqual(selected.name, case.name)
      with patch.dict("os.environ", {
        "RWF_WRITER_ID": writer.writer_id,
        "RWF_SESSION_ID": writer.session_id,
      }):
        outcome = record_manual_result(
          root, 703, candidate, "failed",
          operator="certifier-703", evidence_ref="native-fail-proof",
          cases=(case,),
        )
      self.assertTrue(outcome.completed)
      self.assertEqual(outcome.result, "failed")
      # The canonical version transition changes VERSION in the worktree.
      # A read-model for the *old* candidate must now fail closed.  Preserve
      # the immutable old-candidate JSONL audit as independent evidence.
      from repo_workflow.manual_test_state import ManualSelectionError
      with self.assertRaisesRegex(ManualSelectionError, "changed source inputs"):
        read_manual_case_results(root, 703, candidate, cases=(case,))
      final = LifecycleStore(root).read(703).lifecycle
      self.assertEqual(final.state, "active")
      self.assertFalse(final.dependency_satisfied)
      self.assertEqual(final.history[-1].transition, "reject/reopen")
      self.assertEqual(
        (root / "VERSION").read_text(encoding="utf-8"),
        "1.0.0-issue.703.6.0\n",
      )
      self.assertEqual(fixture.head(), candidate)
      destination_after = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "refs/heads/main"],
        text=True,
      ).strip()
      self.assertEqual(destination_after, destination_before)
      log = root / ".repoworkflow/validation/testResults-703.jsonl"
      events = [json.loads(row) for row in log.read_text().splitlines()]
      self.assertEqual(len(events), 1)
      self.assertEqual(events[0]["manualCase"], case.name)
      self.assertEqual(events[0]["testSHA"], candidate)
      self.assertEqual(events[0]["result"], "failed")
      self.assertEqual(events[0]["operator"], "certifier-703")
      self.assertEqual(events[0]["evidenceRef"], "native-fail-proof")
      self.assertFalse((root / ".repoworkflow/manual/pending-703.json").exists())


  def test_shipped_manual_fail_reports_durable_outcome_after_version_bump(self):
    """Legal FAIL should report its own result, even when old SHA is stale."""
    import json
    from pathlib import Path
    import subprocess
    import tempfile
    import os

    from repo_workflow.lifecycle_store import LifecycleStore
    from repo_workflow.state_store import WriterIdentity
    from tests.support import RepoFixture

    engine = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory) / "consumer"
      root.mkdir()
      fixture = RepoFixture(root, version="1.0.0-issue.703.5.7")
      fixture._run("switch", "-c", "issue-703-actual-manual")
      catalogue = json.loads((engine / ".ci/tests.json").read_text())
      harness = catalogue["tests"][0]["test-harness"]
      catalogue["tests"].append({
        "test-harness": harness,
        "issue-703-manual--NEGATIVE": {
          "type": "manual",
          "instructions": "Check independent negative path",
          "expected_result": "This manual case deliberately fails",
        },
      })
      (root / ".ci/tests.json").write_text(json.dumps(catalogue))
      candidate = fixture.commit("exact manual case candidate")
      identity = WriterIdentity("certifier-703", "operator-live-local")
      store = LifecycleStore(root)
      start = store.transition(703, "start", None, None, identity, None)
      review = store.transition(
        703, "submit-review", candidate, None, identity, start.revision,
      )
      accepted = store.transition(
        703, "accept", candidate, None, identity, review.revision,
      )
      self.assertEqual(accepted.lifecycle.state, "accepted")
      env = dict(os.environ, RWF_WRITER_ID=identity.writer_id,
                 RWF_SESSION_ID=identity.session_id)

      def cli(*args):
        return subprocess.run(
          ["sh", str(engine / "rwf"), "--root", str(root), *args],
          capture_output=True, text=True, env=env,
        )

      selected = cli("test", "integration", "--manual")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      self.assertIn("issue-703-manual--NEGATIVE", selected.stdout)
      negative = cli("test", "failed")
      self.assertNotEqual(negative.returncode, 0)
      # Failure is expected to be terminal, *not* an exception while
      # re-reading the now-obsolete SHA after Q/R changed.
      self.assertIn("Manual integration FAILED", negative.stdout,
                    negative.stderr)
      events = (
        root / ".repoworkflow/validation/testResults-703.jsonl"
      ).read_text().splitlines()
      self.assertEqual(len(events), 1)
      self.assertEqual(json.loads(events[0])["result"], "failed")
      self.assertEqual(
        (root / "VERSION").read_text(encoding="utf-8"),
        "1.0.0-issue.703.6.0\n",
      )
      lifecycle = LifecycleStore(root).read(703).lifecycle
      self.assertEqual(lifecycle.state, "active")
      self.assertFalse(lifecycle.dependency_satisfied)


if __name__ == "__main__":
  unittest.main()
