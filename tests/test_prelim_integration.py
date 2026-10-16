"""Provider-neutral #84 exact PRELIM request negative and replay tests."""
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_workflow import prelim_integration as api


ATTEMPT = "12345678-1234-4234-8234-123456789abc"
CANDIDATE = "a" * 40
BASE = "b" * 40
SOURCE = "c" * 40
VALUE = {
  "attempt": ATTEMPT, "issue": "84",
  "branch": "prelim-main-" + ATTEMPT,
  "source_ref": "refs/heads/issue-84-feature",
  "source_sha": SOURCE, "base_sha": BASE,
  "lifecycle_revision": 0, "bump": "patch",
  "state": "ready", "candidate_sha": CANDIDATE,
  "proposed_version": "0.1.123",
}
IDENTITY = {
  "outcome": "PASS", "attempt": ATTEMPT, "issue": "84",
  "candidate_sha": CANDIDATE, "source_sha": SOURCE,
  "base_sha": BASE,
}
CONFIG = {"repository": {
  "authoritativeRemote": "origin", "integrationBranch": "main",
}}


class Store:
  def __init__(self):
    self.records = {"prelim/identities/" + ATTEMPT: {
      "value": dict(IDENTITY), "revision": 0,
    }}

  def read(self, key):
    return self.records[key]


class IntegrationTests(unittest.TestCase):
  def setUp(self):
    self.store = Store()
    self.states = {}
    self.sent = []
    self.remote = {
      "refs/heads/main": BASE,
      "refs/heads/" + VALUE["branch"]: CANDIDATE,
    }
    self.patches = [
      patch.object(api, "durable_store", return_value=self.store),
      patch.object(api, "_restore_remote_record", return_value={
        "value": dict(VALUE), "revision": 1,
      }),
      patch("repo_workflow.prelim_publication.restore_identity"),
      patch.object(api, "_trusted_inputs"),
      patch.object(api, "_remote_ref", side_effect=lambda root, remote, ref:
                   self.remote.get(ref)),
      patch.object(api, "_state", side_effect=self.read_state),
      patch.object(api, "_save", side_effect=self.write_state),
      patch.object(api, "dispatch_configured", side_effect=self.dispatch),
    ]
    for context in self.patches:
      context.start()
      self.addCleanup(context.stop)

  def read_state(self, root, remote, attempt, suffix):
    return self.states.get(suffix)

  def write_state(self, root, remote, attempt, suffix, payload, base):
    existing = self.states.get(suffix)
    if existing and existing["value"] != payload:
      raise api.PrelimIntegrationError("immutable collision")
    record = existing or {"value": payload, "revision": 0}
    self.states[suffix] = record
    return record

  def dispatch(self, root, request):
    self.sent.append(request)
    params = request["parameters"]
    return {"result": {
      "number": 400, "source_ref": params["source_ref"],
      "target_ref": params["target_ref"],
      "head_sha": params["expected_source_sha"],
      "draft": True,
    }}

  def execute(self, **kwargs):
    return api.request_prelim_integration(
      Path("."), ATTEMPT, CONFIG, repository="owner/repo",
      title="Accept PRELIM", body="Validated exact candidate",
      authorize=lambda *args: True, **kwargs,
    )

  def test_exact_candidate_recorded_distinct_request(self):
    result = self.execute()
    self.assertEqual(result.candidate_sha, CANDIDATE)
    self.assertEqual(result.number, 400)
    self.assertEqual(self.sent[0]["operation"], "pull_request.create")
    self.assertEqual(self.sent[0]["parameters"]["expected_source_sha"], CANDIDATE)
    self.assertEqual(self.states["result"]["value"]["status"],
                     "requested-not-integrated")
    self.assertEqual(len(self.sent), 1)

  def test_replay_does_not_duplicate_provider_mutation(self):
    first = self.execute()
    second = self.execute()
    self.assertEqual(first, second)
    self.assertEqual(len(self.sent), 1)

  def test_unknown_outcome_keeps_intent_and_replays_same_identity(self):
    from repo_workflow.host_mutation_dispatch import HostMutationError
    with patch.object(api, "dispatch_configured",
                      side_effect=HostMutationError("timeout", "unknown_outcome")):
      with self.assertRaises(api.PrelimIntegrationError):
        self.execute()
    self.assertIn("intent", self.states)
    self.assertNotIn("result", self.states)
    successful = self.execute()
    self.assertEqual(successful.request_id,
                     self.states["intent"]["value"]["request_id"])

  def test_bad_identity_rejected_before_provider(self):
    self.store.records["prelim/identities/" + ATTEMPT]["value"]["outcome"] = "FAIL"
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute()
    self.assertEqual(self.sent, [])

  def test_changed_physical_candidate_rejected(self):
    self.remote["refs/heads/" + VALUE["branch"]] = "d" * 40
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute()
    self.assertEqual(self.sent, [])

  def test_moved_destination_rejected(self):
    self.remote["refs/heads/main"] = "d" * 40
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute()
    self.assertEqual(self.sent, [])

  def test_absent_authorization_rejected(self):
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute(authorize=None)
    self.assertEqual(self.sent, [])

  def test_denied_authorization_rejected(self):
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute(authorize=lambda *args: False)
    self.assertEqual(self.sent, [])

  def test_changed_title_cannot_reuse_request(self):
    self.execute()
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute(title="A different requested PR")
    self.assertEqual(len(self.sent), 1)

  def test_changed_prelim_identity_cannot_reuse_request(self):
    self.execute()
    self.store.records["prelim/identities/" + ATTEMPT]["revision"] = 9
    with self.assertRaises(api.PrelimIntegrationError):
      self.execute()
    self.assertEqual(len(self.sent), 1)

  def test_task_issue_cannot_be_returned_as_integration_request(self):
    with patch.object(api, "dispatch_configured",
                      return_value={"result": {"number": 84}}):
      with self.assertRaises(api.PrelimIntegrationError):
        self.execute()
    self.assertNotIn("result", self.states)

  def test_mutation_failure_never_publishes_result(self):
    from repo_workflow.host_mutation_dispatch import HostMutationError
    with patch.object(api, "dispatch_configured",
                      side_effect=HostMutationError("refused", "unauthorized")):
      with self.assertRaises(api.PrelimIntegrationError):
        self.execute()
    self.assertNotIn("result", self.states)

  def test_post_mutation_destination_movement_not_recorded(self):
    def move(*args):
      self.remote["refs/heads/main"] = "d" * 40
      return self.dispatch(*args)
    with patch.object(api, "dispatch_configured", side_effect=move):
      with self.assertRaises(api.PrelimIntegrationError):
        self.execute()
    self.assertNotIn("result", self.states)


if __name__ == "__main__":
  unittest.main()
