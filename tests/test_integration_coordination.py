"""Black-box claim/release state and concurrency oracles."""
import unittest

from repo_workflow.integration_coordination import (
  CoordinationError, DestinationLease, claim_prelim, release_prelim,
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

  def read_destination_lease(self, destination):
    return self.leases.get(
      destination, DestinationLease(destination, 0, None, None))

  def compare_and_set_destination_lease(self, before, after):
    if self.fail_cas or self.read_destination_lease(before.destination) != before:
      return False
    self.leases[before.destination] = after
    return True

  def read_attempt_result(self, guid):
    return self.outcomes.get(guid)


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
      release_prelim(self.p, one, "worker-A", terminal_result="deferred-mit")
    self.p.outcomes[GUID1] = "deferred-mit"
    released = release_prelim(self.p, one, "worker-A", terminal_result="deferred-mit")
    self.assertIsNone(released.active_guid)

  def test_released_claim_cannot_be_replayed(self):
    one = claim_prelim(self.p, self.a, "worker-A")
    self.p.outcomes[GUID1] = "integrated"
    release_prelim(self.p, one, "worker-A", terminal_result="integrated")
    with self.assertRaises(CoordinationError):
      release_prelim(self.p, one, "worker-A", terminal_result="integrated")


if __name__ == "__main__":
  unittest.main()
