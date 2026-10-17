"""Immutable remote PRELIM queue discovery contract."""

import unittest

from repo_workflow.prelim_queue import (
  PrelimQueueError, discover_ready_prelims, parse_ready_prelim,
  verify_immutable_prelims,
)


A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
SHA_A = "a" * 40
SHA_B = "b" * 40


def ref(umbrella, destination, guid):
  return f"refs/heads/PRELIM-{umbrella}/{destination}-{guid}"


class PrelimQueueTests(unittest.TestCase):
  def test_published_ref_is_ready_without_marker(self):
    candidate = parse_ready_prelim(ref("issue-123", "main", A), SHA_A)
    self.assertEqual(candidate.umbrella, "issue-123")
    self.assertEqual(candidate.destination, "main")
    self.assertEqual(candidate.guid, A)
    self.assertEqual(candidate.sha, SHA_A)

  def test_different_umbrellas_share_one_destination(self):
    refs = {
      ref("issue-123", "main", A): SHA_A,
      ref("issue-456", "main", B): SHA_B,
    }
    self.assertEqual(
      {c.destination for c in discover_ready_prelims(refs)}, {"main"})

  def test_nested_branch_destinations_remain_distinct(self):
    refs = {
      ref("issue-123", "rc/1.2", A): SHA_A,
      ref("issue-123", "issue-456", B): SHA_B,
    }
    self.assertEqual(
      {c.destination for c in discover_ready_prelims(refs)},
      {"rc/1.2", "issue-456"})

  def test_unrelated_refs_are_not_submissions(self):
    self.assertIsNone(parse_ready_prelim("refs/heads/main", SHA_A))
    self.assertIsNone(parse_ready_prelim(
      "refs/heads/INT-ATTEMPT-issue-123/main-" + A, SHA_A))

  def test_reserved_malformed_refs_fail_closed(self):
    wrong = (
      "refs/heads/PRELIM-issue-0/main-" + A,
      "refs/heads/PRELIM-issue-123/main-not-a-guid",
      "refs/heads/PRELIM-issue-123/../main-" + A,
      "refs/heads/PRELIM-issue-123/main//other-" + A,
      "refs/heads/PRELIM-issue-123/main-" + A.upper(),
    )
    for name in wrong:
      with self.subTest(ref=name):
        with self.assertRaises(PrelimQueueError):
          parse_ready_prelim(name, SHA_A)
    with self.assertRaises(PrelimQueueError):
      parse_ready_prelim(ref("issue-123", "main", A), "bad-sha")

  def test_same_guid_two_branches_is_rejected(self):
    with self.assertRaises(PrelimQueueError):
      discover_ready_prelims({
        ref("issue-123", "main", A): SHA_A,
        ref("issue-456", "rc", A): SHA_B,
      })

  def test_ref_sha_remains_immutable(self):
    name = ref("issue-123", "main", A)
    self.assertEqual(len(verify_immutable_prelims(
      {name: SHA_A}, {name: SHA_A})), 1)
    with self.assertRaisesRegex(PrelimQueueError, "changed"):
      verify_immutable_prelims({name: SHA_A}, {name: SHA_B})

  def test_published_ref_cannot_disappear_without_cleanup(self):
    with self.assertRaisesRegex(PrelimQueueError, "disappeared"):
      verify_immutable_prelims(
        {ref("issue-123", "main", A): SHA_A}, {})

  def test_new_submissions_can_join_without_mutating_old(self):
    old = ref("issue-123", "main", A)
    new = ref("issue-123", "main", C)
    ready = verify_immutable_prelims(
      {old: SHA_A}, {old: SHA_A, new: SHA_B})
    self.assertEqual(len(ready), 2)

  def test_result_order_is_deterministic_not_priority(self):
    first = ref("issue-123", "main", B)
    second = ref("issue-123", "main", A)
    ready = discover_ready_prelims({first: SHA_B, second: SHA_A})
    self.assertEqual([x.ref for x in ready], sorted((first, second)))


if __name__ == "__main__":
  unittest.main()
