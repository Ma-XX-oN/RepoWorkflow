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
    with self.assertRaisesRegex(CoordinationError, "UNKNOWN"):
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


  def test_memoized_provider_reads_do_not_hide_new_ready_ref(self):
    physical=self.host.request
    cache={}

    def cache_read(op,key,params):
      if op in {"refs.list","lease.read","attempt.read",
                "mit.deferred.read","mit.resume.read"}:
        if key not in cache:
          cache[key]=physical(op,key,params)
        return cache[key]
      return physical(op,key,params)

    self.host.request=cache_read
    self.assertEqual(self.coord.read_ready_prelims(),(self.ready,))
    other=self.ready.ref.replace(GUID,"22222222-2222-4222-8222-222222222222")
    self.host.refs[other]="b"*40
    fresh=self.coord.read_ready_prelims()
    self.assertEqual(len(fresh),2)
    self.assertNotEqual(fresh,(self.ready,))
    self.assertEqual(len(cache),2)

  def test_memoized_provider_read_observes_changed_destination_lease(self):
    physical=self.host.request
    cache={}

    def cache_read(op,key,params):
      if op=="lease.read":
        if key not in cache:
          cache[key]=physical(op,key,params)
        return cache[key]
      return physical(op,key,params)

    self.host.request=cache_read
    before=self.coord.read_destination_lease("main")
    self.host.lease.update(generation=1,guid=GUID,holder="other-worker")
    after=self.coord.read_destination_lease("main")
    self.assertEqual(before.generation,0)
    self.assertEqual(after.generation,1)
    self.assertEqual(after.holder,"other-worker")
    self.assertEqual(len(cache),2)

  def test_memoized_provider_read_observes_new_terminal(self):
    physical=self.host.request
    cache={}

    def cache_read(op,key,params):
      if op=="attempt.read":
        if key not in cache:
          cache[key]=physical(op,key,params)
        return cache[key]
      return physical(op,key,params)

    self.host.request=cache_read
    self.assertIsNone(self.coord.read_attempt_result(GUID))
    self.host.terminal={
      "repository":"Org/Repo","guid":GUID,"status":"integrated"}
    self.assertEqual(self.coord.read_attempt_result(GUID),"integrated")
    self.assertEqual(len(cache),2)

  def test_memoized_provider_read_observes_mit_approval(self):
    physical=self.host.request
    cache={}

    def cache_read(op,key,params):
      if op=="mit.resume.read":
        if key not in cache:
          cache[key]=physical(op,key,params)
        return cache[key]
      return physical(op,key,params)

    self.host.request=cache_read
    self.assertIsNone(self.coord.read_mit_resume_authorization(GUID,"main"))
    self.host.resume={
      "repository":"Org/Repo", "guid":GUID, "destination":"main",
      "prelim_sha":A, "expected_generation":2,
      "deferred_evidence_ref":"event-1",
      "evidence_ref":"approval-1","approved":True}
    approval=self.coord.read_mit_resume_authorization(GUID,"main")
    self.assertTrue(approval.approved)
    self.assertEqual(len(cache),2)


  def test_lost_claim_cas_ack_reconciles_exact_durable_lease(self):
    original=self.host.request
    def commit_then_lose_ack(op,key,params):
      if op=="lease.cas":
        original(op,key,params)
        raise TimeoutError("provider wrote lease; ACK lost")
      return original(op,key,params)
    self.host.request=commit_then_lose_ack
    lease=claim_prelim(self.coord,self.ready,"worker-A")
    self.assertEqual(lease.generation,1)
    self.assertEqual(self.host.lease["guid"],GUID)
    self.assertEqual(self.coord.read_destination_lease("main"),lease)

  def test_lost_release_cas_ack_recovers_without_second_write(self):
    claim=claim_prelim(self.coord,self.ready,"worker-A")
    self.host.terminal={
      "repository":"Org/Repo","guid":GUID,"status":"integrated"}
    original=self.host.request
    calls=[]
    def commit_then_lose_ack(op,key,params):
      if op=="lease.cas":
        calls.append(key)
        original(op,key,params)
        raise TimeoutError("provider released lease; ACK lost")
      return original(op,key,params)
    self.host.request=commit_then_lose_ack
    released=release_prelim(
      self.coord,claim,"worker-A",terminal_result="integrated")
    self.assertEqual(len(calls),1)
    self.assertEqual(released.generation,2)
    self.assertIsNone(released.active_guid)
    self.assertEqual(self.coord.read_destination_lease("main"),released)

  def test_forged_positive_lease_receipt_without_write_is_denied(self):
    original=self.host.request
    def forged(op,key,params):
      if op=="lease.cas":
        return {
          "destination":params["destination"],
          "generation":params["expected_generation"]+1,
          "guid":params["guid"],"holder":params["holder"]}
      return original(op,key,params)
    self.host.request=forged
    with self.assertRaisesRegex(CoordinationError,"readback differs"):
      claim_prelim(self.coord,self.ready,"worker-A")
    self.assertEqual(self.host.lease["generation"],0)

  def test_changed_lease_after_lost_ack_is_unknown_not_success(self):
    original=self.host.request
    def replaced(op,key,params):
      if op=="lease.cas":
        original(op,key,params)
        self.host.lease["holder"]="other-worker"
        raise TimeoutError("ACK lost and another actor changed lease")
      return original(op,key,params)
    self.host.request=replaced
    with self.assertRaisesRegex(CoordinationError,"UNKNOWN"):
      claim_prelim(self.coord,self.ready,"worker-A")
    self.assertEqual(self.host.lease["holder"],"other-worker")


if __name__ == "__main__":
  unittest.main()
