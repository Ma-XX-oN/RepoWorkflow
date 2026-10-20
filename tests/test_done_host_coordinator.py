"""Black-box #681 host bridge tests, no client-supplied integration PASS."""
import unittest

from repo_workflow.done_host_coordinator import IntegrationHostCoordinator
from repo_workflow.integration_coordination import (
  CoordinationError, claim_prelim, release_prelim,
)
from repo_workflow.prelim_queue import parse_ready_prelim


GUID = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/PRELIM-issue-123/main-{GUID}"
A = "a" * 40


class FakeHost:
  repository = "Org/Repo"

  def __init__(self):
    self.refs = {REF: A}
    self.lease = {"destination": "main", "generation": 0,
                  "guid": None, "holder": None}
    self.terminal = None
    self.defer = None
    self.resume = None
    self.requests = []
    self.fail_cas = False

  def request(self, operation, request_id, params):
    self.requests.append((operation, request_id, params))
    if operation == "refs.list":
      assert params == {"prefix": "refs/heads/PRELIM-"}
      return {"refs": dict(self.refs)}
    if operation == "lease.read":
      return dict(self.lease)
    if operation == "lease.cas":
      if self.fail_cas:
        raise TimeoutError("provider response lost")
      if (self.lease["generation"] != params["expected_generation"]
          or self.lease["guid"] != params["expected_guid"]
          or self.lease["holder"] != params["expected_holder"]):
        raise CoordinationError("compare-and-swap rejected")
      self.lease = {
        "destination": params["destination"],
        "generation": params["expected_generation"] + 1,
        "guid": params["guid"], "holder": params["holder"],
      }
      return dict(self.lease)
    if operation == "attempt.read":
      return {"guid": params["guid"], "record": self.terminal}
    if operation == "mit.deferred.read":
      return {"guid": params["guid"],
              "destination": params["destination"], "event": self.defer}
    if operation == "mit.resume.read":
      return {"guid": params["guid"], "destination": params["destination"],
              "authorization": self.resume}
    raise AssertionError(f"unexpected {operation}")


class ProviderCoordinatorTests(unittest.TestCase):
  def setUp(self):
    self.host = FakeHost()
    self.coord = IntegrationHostCoordinator(self.host)
    self.ready = parse_ready_prelim(REF, A)

  def test_provider_discovery_and_claim_release(self):
    self.assertEqual(self.coord.read_ready_prelims(), (self.ready,))
    first = claim_prelim(self.coord, self.ready, "worker-A")
    self.assertEqual((first.generation, first.active_guid), (1, GUID))
    with self.assertRaisesRegex(CoordinationError, "another coordinator"):
      claim_prelim(self.coord, self.ready, "worker-B")
    self.host.terminal = {
      "repository": "Org/Repo", "guid": GUID, "status": "integrated"}
    last = release_prelim(
      self.coord, first, "worker-A", terminal_result="integrated")
    self.assertEqual(last.generation, 2)
    self.assertIsNone(last.active_guid)
    with self.assertRaisesRegex(CoordinationError, "terminal"):
      claim_prelim(self.coord, self.ready, "worker-B")

  def test_changed_original_prelim_inventory_refused(self):
    self.host.refs[REF] = "b" * 40
    changed = self.coord.read_ready_prelims()
    self.assertNotEqual(changed, (self.ready,))

  def test_mit_timeout_restarts_after_exact_approval(self):
    first = claim_prelim(self.coord, self.ready, "worker-A")
    self.host.defer = {
      "repository": "Org/Repo", "guid": GUID, "destination": "main",
      "prelim_sha": A, "lease_generation": 1,
      "evidence_ref": "defer-1", "reason": "timeout"}
    release_prelim(self.coord, first, "worker-A",
                   terminal_result="deferred-mit", submission=self.ready)
    with self.assertRaisesRegex(CoordinationError, "approved"):
      claim_prelim(self.coord, self.ready, "worker-B")
    self.host.resume = {
      "repository": "Org/Repo", "guid": GUID, "destination": "main",
      "prelim_sha": A, "expected_generation": 2,
      "deferred_evidence_ref": "defer-1", "evidence_ref": "approved-1",
      "approved": True}
    second = claim_prelim(self.coord, self.ready, "worker-B")
    self.assertEqual(second.generation, 3)
    self.assertEqual(second.holder, "worker-B")

  def test_stale_defer_identity_refused(self):
    self.host.defer = {
      "repository": "Other/Repo", "guid": GUID,
      "destination": "main", "prelim_sha": A, "lease_generation": 1,
      "evidence_ref": "x", "reason": "timeout"}
    with self.assertRaisesRegex(CoordinationError, "provenance"):
      claim_prelim(self.coord, self.ready, "worker-A")
    self.assertEqual(self.host.lease["generation"], 0)

  def test_lost_lease_cas_fails_closed(self):
    self.host.fail_cas = True
    with self.assertRaisesRegex(CoordinationError, "UNKNOWN"):
      claim_prelim(self.coord, self.ready, "worker-A")
    self.assertEqual(self.host.lease["generation"], 0)

  def test_foreign_terminal_denied(self):
    self.host.terminal = {
      "repository": "Foreign/Repo", "guid": GUID, "status": "integrated"}
    with self.assertRaisesRegex(CoordinationError, "unverified"):
      claim_prelim(self.coord, self.ready, "worker-A")
    self.assertEqual(self.host.lease["generation"], 0)

  def test_claim_and_release_use_unique_durable_operation_keys(self):
    first = claim_prelim(self.coord, self.ready, "worker-A")
    self.host.terminal = {
      "repository": "Org/Repo", "guid": GUID, "status": "rejected"}
    release_prelim(self.coord, first, "worker-A", terminal_result="rejected")
    keys = [key for operation, key, _ in self.host.requests
            if operation == "lease.cas"]
    self.assertEqual(len(keys), 2)
    self.assertEqual(len(set(keys)), 2)


if __name__ == "__main__":
  unittest.main()
