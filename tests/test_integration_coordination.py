"""Black-box claim/release state and concurrency oracles."""
import unittest

from repo_workflow.integration_coordination import (
  CoordinationError, DestinationLease, MitDeferredEvent,
  MitResumeAuthorization,
  claim_prelim, release_prelim,
)
from repo_workflow.prelim_queue import parse_ready_prelim

GUID1 = "11111111-1111-4111-8111-111111111111"
GUID2 = "22222222-2222-4222-8222-222222222222"


def candidate(issue, destination, guid):
  return parse_ready_prelim(
    f"refs/heads/PRELIM-issue-{issue}/{destination}-{guid}", "a"*40)


class CasProvider:
  def __init__(self):
    self.leases = {}
    self.outcomes = {}
    self.fail_cas = False
    self.approvals = {}
    self.deferred_events = {}
    self.rechecks = 0

  def read_destination_lease(self, destination):
    return self.leases.get(
      destination, DestinationLease(destination, 0, None, None))

  def compare_and_set_destination_lease(self, before, after):
    if self.fail_cas or self.read_destination_lease(before.destination) != before:
      return False
    self.leases[before.destination] = after
    return True

  def read_attempt_result(self, guid):
    self.rechecks += 1
    return self.outcomes.get(guid)

  def read_mit_deferred_event(self, guid, destination):
    return self.deferred_events.get((guid, destination))

  def read_mit_resume_authorization(self, guid, destination):
    return self.approvals.get((guid, destination))


class IntegrationCoordinationTests(unittest.TestCase):
  def setUp(self):
    self.p = CasProvider()
    self.a = candidate(123, "main", GUID1)
    self.b = candidate(456, "main", GUID2)

  def test_first_claim_wins_same_destination(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    self.assertEqual(one.active_guid, GUID1)
    with self.assertRaisesRegex(CoordinationError, "another coordinator"):
      claim_prelim(self.p, self.b, "worker-B")

  def test_distinct_destinations_are_independent(self):
    other = candidate(456, "issue-100", GUID2)
    first = claim_prelim(self.p, self.a, "worker-A")
    second = claim_prelim(self.p, other, "worker-B")
    self.assertNotEqual(first.destination, second.destination)

  def test_stale_cas_does_not_create_claim(self):
    self.p.fail_cas = True
    with self.assertRaisesRegex(CoordinationError, "lost"):
      claim_prelim(self.p, self.a, "worker-A")
    self.assertIsNone(self.p.read_destination_lease("main").active_guid)

  def test_existing_terminal_prevents_replay(self):
    self.p.outcomes[GUID1] = "integrated"
    with self.assertRaisesRegex(CoordinationError, "already"):
      claim_prelim(self.p, self.a, "worker-A")

  def test_release_requires_persisted_result(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    with self.assertRaisesRegex(CoordinationError, "readback"):
      release_prelim(self.p, one, "worker-A", terminal_result="integrated")
    self.assertEqual(self.p.read_destination_lease("main"), one)

  def test_release_allows_next_pending_attempt(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    self.p.outcomes[GUID1] = "integrated"
    freed = release_prelim(self.p, one, "worker-A", terminal_result="integrated")
    self.assertIsNone(freed.active_guid)
    two = claim_prelim(self.p, self.b, "worker-B")
    self.assertEqual(two.active_guid, GUID2)
    self.assertEqual(two.generation, 3)

  def test_wrong_worker_cannot_release(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    self.p.outcomes[GUID1] = "integrated"
    with self.assertRaises(CoordinationError):
      release_prelim(self.p, one, "worker-B", terminal_result="integrated")

  def test_deferred_mit_requires_durable_defer(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    with self.assertRaises(CoordinationError):
      release_prelim(self.p, one, "worker-A", terminal_result="deferred-mit",submission=self.a)
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,1,"mit-defer-1","timeout")
    released = release_prelim(self.p, one, "worker-A", terminal_result="deferred-mit",submission=self.a)
    self.assertIsNone(released.active_guid)

  def test_deferred_release_denies_wrong_candidate_sha(self):
    one=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main","b"*40,one.generation,"mit-defer-wrong-sha","timeout")
    with self.assertRaisesRegex(CoordinationError,"readback"):
      release_prelim(self.p,one,"worker-A",
                     terminal_result="deferred-mit",submission=self.a)
    self.assertEqual(self.p.read_destination_lease("main"),one)

  def test_deferred_release_requires_submission(self):
    one=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,one.generation,"mit-defer-1","timeout")
    with self.assertRaisesRegex(CoordinationError,"exact PRELIM"):
      release_prelim(self.p,one,"worker-A",terminal_result="deferred-mit")
    self.assertEqual(self.p.read_destination_lease("main"),one)

  def test_mit_timeout_is_not_final_failure(self):
    claim=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,claim.generation,"timeout-1","timeout")
    release_prelim(self.p,claim,"worker-A",terminal_result="deferred-mit",
                   submission=self.a)
    self.assertIsNone(self.p.read_attempt_result(GUID1))
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,2,"timeout-1","manual-approval",True)
    resumed=claim_prelim(self.p,self.a,"worker-B")
    self.assertEqual(resumed.generation,3)

  def test_malformed_provider_defer_reason_fails_closed(self):
    claim=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,claim.generation,"bad",["timeout"])
    with self.assertRaises(CoordinationError):
      release_prelim(self.p,claim,"worker-A",terminal_result="deferred-mit",
                     submission=self.a)
    self.assertEqual(self.p.read_destination_lease("main"),claim)

  def test_invalid_defer_reason_does_not_release_lease(self):
    claim=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,claim.generation,"fake","failed")
    with self.assertRaisesRegex(CoordinationError,"readback"):
      release_prelim(self.p,claim,"worker-A",terminal_result="deferred-mit",
                     submission=self.a)
    self.assertEqual(self.p.read_destination_lease("main"),claim)

  def test_deferred_mit_restart_requires_exact_provider_approval(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,1,"mit-defer-1","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",submission=self.a)
    with self.assertRaisesRegex(CoordinationError,"approved"):
      claim_prelim(self.p,self.a,"worker-B")
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,2,"mit-defer-1","mit-approval-1",True)
    resumed=claim_prelim(self.p,self.a,"worker-B")
    self.assertEqual(resumed.active_guid,GUID1)
    self.assertEqual(resumed.generation,3)
    with self.assertRaisesRegex(CoordinationError,"another coordinator"):
      claim_prelim(self.p,self.a,"worker-C")

  def test_deferred_resume_foreign_sha_or_destination_denied(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,1,"mit-defer-1","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",submission=self.a)
    for approval in (
      MitResumeAuthorization(GUID1,"main","b"*40,2,"mit-defer-1","proof",True),
      MitResumeAuthorization(GUID1,"other",self.a.sha,2,"mit-defer-1","proof",True),
      MitResumeAuthorization(GUID2,"main",self.a.sha,2,"mit-defer-1","proof",True),
      MitResumeAuthorization(GUID1,"main",self.a.sha,2,"mit-defer-1","",True),
      MitResumeAuthorization(GUID1,"main",self.a.sha,2,"mit-defer-1","proof",False),
    ):
      self.p.approvals[(GUID1,"main")]=approval
      with self.subTest(approval=approval):
        with self.assertRaisesRegex(CoordinationError,"approved"):
          claim_prelim(self.p,self.a,"worker-B")
      self.assertIsNone(self.p.read_destination_lease("main").active_guid)

  def test_approval_for_wrong_defer_event_denied(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,first.generation,"new-defer","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",
                   submission=self.a)
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,2,"old-defer","approval",True)
    with self.assertRaisesRegex(CoordinationError,"approved"):
      claim_prelim(self.p,self.a,"worker-B")
    self.assertIsNone(self.p.read_destination_lease("main").active_guid)

  def test_approval_changed_during_claim_is_rejected(self):
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,1,"mit-defer-1","timeout")
    approved=MitResumeAuthorization(GUID1,"main",self.a.sha,2,"mit-defer-1","proof",True)
    self.p.approvals[(GUID1,"main")]=approved
    original=self.p.compare_and_set_destination_lease
    def revoke(before,after):
      outcome=original(before,after)
      self.p.approvals.pop((GUID1,"main"),None)
      return outcome
    self.p.compare_and_set_destination_lease=revoke
    with self.assertRaisesRegex(CoordinationError,"approved"):
      claim_prelim(self.p,self.a,"worker-B")
    # The claimed lease must be reconciled: never assume an automatic rollback.
    self.assertEqual(self.p.read_destination_lease("main").active_guid,GUID1)

  def test_old_approval_cannot_resume_after_another_defer(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,1,"mit-defer-1","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",submission=self.a)
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,2,"mit-defer-1","mit-approval-1",True)
    resumed=claim_prelim(self.p,self.a,"worker-B")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,resumed.generation,"mit-defer-2","awaiting-manual")
    release_prelim(self.p,resumed,"worker-B",terminal_result="deferred-mit",submission=self.a)
    with self.assertRaisesRegex(CoordinationError,"approved"):
      claim_prelim(self.p,self.a,"worker-C")
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,4,"mit-defer-2","mit-approval-2",True)
    next_claim=claim_prelim(self.p,self.a,"worker-C")
    self.assertEqual(next_claim.generation,5)

  def test_defer_event_read_unknown_never_claims(self):
    original=self.p.read_mit_deferred_event
    def fail(guid,destination):
      raise RuntimeError("provider unavailable")
    self.p.read_mit_deferred_event=fail
    with self.assertRaisesRegex(CoordinationError,"UNKNOWN"):
      claim_prelim(self.p,self.a,"worker-A")
    self.p.read_mit_deferred_event=original
    self.assertIsNone(self.p.read_destination_lease("main").active_guid)

  def test_defer_event_changed_during_cas_requires_recovery(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,first.generation,"defer-1","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",
                   submission=self.a)
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,2,"defer-1","approve-1",True)
    original=self.p.compare_and_set_destination_lease
    def mutate_event(before,after):
      result=original(before,after)
      self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
        GUID1,"main",self.a.sha,first.generation,
        "defer-changed","timeout")
      return result
    self.p.compare_and_set_destination_lease=mutate_event
    with self.assertRaisesRegex(CoordinationError,"changed"):
      claim_prelim(self.p,self.a,"worker-B")
    self.assertEqual(self.p.read_destination_lease("main").holder,"worker-B")

  def test_deferred_submission_waits_behind_other_umbrella(self):
    first=claim_prelim(self.p,self.a,"worker-A")
    self.p.deferred_events[(GUID1,"main")]=MitDeferredEvent(
      GUID1,"main",self.a.sha,first.generation,"defer-1","timeout")
    release_prelim(self.p,first,"worker-A",terminal_result="deferred-mit",
                   submission=self.a)
    other=claim_prelim(self.p,self.b,"worker-B")
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,other.generation,"defer-1","approve-1",True)
    with self.assertRaisesRegex(CoordinationError,"another coordinator"):
      claim_prelim(self.p,self.a,"worker-C")

  def test_terminal_result_cannot_reuse_deferred_approval(self):
    self.p.outcomes[GUID1]="integrated"
    self.p.approvals[(GUID1,"main")]=MitResumeAuthorization(
      GUID1,"main",self.a.sha,0,"none","old-approval",True)
    with self.assertRaisesRegex(CoordinationError,"terminal"):
      claim_prelim(self.p,self.a,"worker-B")

  def test_released_claim_cannot_be_replayed(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    self.p.outcomes[GUID1] = "integrated"
    release_prelim(self.p, one, "worker-A", terminal_result="integrated")
    with self.assertRaises(CoordinationError):
      release_prelim(self.p, one, "worker-A", terminal_result="integrated")


if __name__ == "__main__":
  unittest.main()
