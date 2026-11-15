"""Immutable remote PRELIM queue discovery contract."""

import unittest

from repo_workflow.prelim_queue import (
  PrelimQueueError, discover_ready_prelims, parse_ready_prelim,
  verify_immutable_prelims,
)


A = "0.1"
B = "0.2"
C = "0.3"
SHA_A = "a" * 40
SHA_B = "b" * 40


def ref(umbrella, destination, version):
  """Name depends on issue/version; destination is supplied independently."""
  return f"refs/heads/PRELIM-{umbrella}.{version}"


class PrelimQueueTests(unittest.TestCase):
  def test_published_ref_is_ready_without_marker(self):
    candidate = parse_ready_prelim(ref("issue-123", "main", A), SHA_A, destination="main")
    self.assertEqual(candidate.umbrella, "issue-123")
    self.assertEqual(candidate.destination, "main")
    self.assertEqual(candidate.version_order, (0, 1))
    self.assertEqual(candidate.sha, SHA_A)

  def test_different_umbrellas_share_one_destination(self):
    refs = {
      ref("issue-123", "main", A): SHA_A,
      ref("issue-456", "main", B): SHA_B,
    }
    self.assertEqual(
      {c.destination for c in discover_ready_prelims(refs)}, {""})

  def test_nested_branch_destinations_remain_distinct(self):
    refs = (
      parse_ready_prelim(ref("issue-123", "rc/1.2", A), SHA_A, destination="rc/1.2"),
      parse_ready_prelim(ref("issue-123", "issue-456", B), SHA_B, destination="issue-456"),
    )
    self.assertEqual(
      {c.destination for c in refs},
      {"rc/1.2", "issue-456"})

  def test_unrelated_refs_are_not_submissions(self):
    self.assertIsNone(parse_ready_prelim("refs/heads/main", SHA_A))
    self.assertIsNone(parse_ready_prelim(
      "refs/heads/issue-123-work", SHA_A))

  def test_reserved_malformed_refs_fail_closed(self):
    wrong = (
      "refs/heads/PRELIM-issue-0/main-" + A,
      "refs/heads/PRELIM-issue-123/main-not-a-guid",
      "refs/heads/PRELIM-issue-123/../main-" + A,
      "refs/heads/PRELIM-issue-123/main//other-" + A,
      "refs/heads/PRELIM-issue-123/main-" + ("a" * 8 + "-" + A[9:]).upper(),
    )
    for name in wrong:
      with self.subTest(ref=name):
        with self.assertRaises(PrelimQueueError):
          parse_ready_prelim(name, SHA_A)
    with self.assertRaises(PrelimQueueError):
      parse_ready_prelim(ref("issue-123", "main", A), "bad-sha")

  def test_same_version_suffix_in_two_issues_is_independent(self):
    ready = discover_ready_prelims({
      ref("issue-123", "main", A): SHA_A,
      ref("issue-456", "rc", A): SHA_B,
    })
    self.assertEqual(len(ready), 2)
    self.assertNotEqual(ready[0].guid, ready[1].guid)

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

  def test_terminal_evidence_permits_only_matching_retired_ref(self):
    ref_name = ref("issue-123", "main", A)
    self.assertEqual(
      verify_immutable_prelims(
        {ref_name: SHA_A}, {}, terminal_refs={ref_name: SHA_A}), ())
    with self.assertRaises(PrelimQueueError):
      verify_immutable_prelims(
        {ref_name: SHA_A}, {}, terminal_refs={ref_name: SHA_B})
    with self.assertRaises(PrelimQueueError):
      verify_immutable_prelims(
        {ref_name: SHA_A}, {ref_name: SHA_B},
        terminal_refs={ref_name: SHA_A})

  def test_result_order_is_deterministic_not_priority(self):
    first = ref("issue-123", "main", B)
    second = ref("issue-123", "main", A)
    ready = discover_ready_prelims({first: SHA_B, second: SHA_A})
    self.assertEqual([x.ref for x in ready], sorted((first, second)))


if __name__ == "__main__":
  unittest.main()
