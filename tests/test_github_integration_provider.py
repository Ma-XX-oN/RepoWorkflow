"""Isolated provider tests for GitHub PRELIM and INT-ATTEMPT primitives."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_host_github_integration import (
  IntegrationProviderError, create_int_attempt, inventory_ready_refs,
)

SHA = "a"*40
REF = ("refs/heads/INT-ATTEMPT-issue-123/"
       "main-11111111-1111-4111-8111-111111111111")


class Missing(Exception):
  code = "not_found"


class FakeBackend:
  def __init__(self):
    self.refs = {}
    self.fresh = True
    self.drop_reply = False
    self.calls = []

  def get(self, route):
    if route.startswith("git/matching-refs"):
      return [{"ref": key, "object": {"sha": value}}
              for key, value in self.refs.items()
              if key.startswith("refs/heads/PRELIM-")]
    ref = "refs/" + route.removeprefix("git/ref/")
    if ref not in self.refs:
      raise Missing()
    return {"ref": ref, "object": {"sha": self.refs[ref]}}

  def post(self, route, body):
    self.calls.append((route, body))
    self.refs[body["ref"]] = body["sha"]
    if self.drop_reply:
      raise TimeoutError("lost response")

  def reserve(self, request):
    return self.fresh


class GithubIntegrationProviderTests(unittest.TestCase):
  def setUp(self):
    self.backend = FakeBackend()
    self.request = {"parameters": {"ref": REF, "sha": SHA}}

  def test_empty_inventory(self):
    self.assertEqual(inventory_ready_refs(self.backend), {})

  def test_exact_inventory(self):
    name = "refs/heads/PRELIM-issue-123/main-guid"
    self.backend.refs[name] = SHA
    self.assertEqual(inventory_ready_refs(self.backend), {name: SHA})

  def test_create_is_read_back(self):
    result = create_int_attempt(self.backend, self.request, authorized=True)
    self.assertEqual(result[0], "applied")
    self.assertEqual(self.backend.refs[REF], SHA)

  def test_denied_actor_cannot_write(self):
    with self.assertRaises(IntegrationProviderError):
      create_int_attempt(self.backend, self.request, authorized=False)
    self.assertEqual(self.backend.calls, [])

  def test_reserved_retry_cannot_change_sha(self):
    self.backend.fresh = False
    self.backend.refs[REF] = "b"*40
    with self.assertRaises(IntegrationProviderError):
      create_int_attempt(self.backend, self.request, authorized=True)

  def test_reservation_survives_crash_before_ref_creation(self):
    self.backend.fresh = False
    self.assertNotIn(REF, self.backend.refs)
    status, result = create_int_attempt(
      self.backend, self.request, authorized=True)
    self.assertEqual(status, "applied")
    self.assertEqual(result, {"ref": REF, "sha": SHA})
    self.assertEqual(self.backend.refs[REF], SHA)
    self.assertEqual(create_int_attempt(
      self.backend, self.request, authorized=True)[0], "unchanged")

  def test_reserved_idempotent_readback(self):
    self.backend.fresh = False
    self.backend.refs[REF] = SHA
    self.assertEqual(create_int_attempt(
      self.backend, self.request, authorized=True)[0], "unchanged")
    self.assertEqual(self.backend.calls, [])

  def test_lost_reply_can_reconcile_matching_ref(self):
    self.backend.drop_reply = True
    self.assertEqual(create_int_attempt(
      self.backend, self.request, authorized=True)[0], "applied")

  def test_ref_collision_does_not_write(self):
    self.backend.refs[REF] = "b"*40
    with self.assertRaises(IntegrationProviderError):
      create_int_attempt(self.backend, self.request, authorized=True)
    self.assertEqual(self.backend.calls, [])

  def test_inventory_across_two_pages(self):
    calls = []
    def get(route):
      calls.append(route)
      page = int(route.split("page=")[-1])
      values = range(100) if page == 1 else range(100, 102)
      return [{"ref": f"refs/heads/PRELIM-issue-123/x{index}",
               "object": {"sha": SHA}} for index in values]
    self.backend.get = get
    self.assertEqual(len(inventory_ready_refs(self.backend)), 102)
    self.assertEqual(len(calls), 2)

  def test_inventory_rejects_repeated_pages(self):
    self.backend.get = lambda route: [
      {"ref": f"refs/heads/PRELIM-issue-123/x{index}",
       "object": {"sha": SHA}} for index in range(100)]
    with self.assertRaisesRegex(IntegrationProviderError, "identity"):
      inventory_ready_refs(self.backend)

  def test_inventory_rejects_pagination_bound(self):
    def get(route):
      page = int(route.split("page=")[-1])
      return [{"ref": f"refs/heads/PRELIM-issue-123/p{page}-x{index}",
               "object": {"sha": SHA}} for index in range(100)]
    self.backend.get = get
    with self.assertRaisesRegex(IntegrationProviderError, "bound"):
      inventory_ready_refs(self.backend, max_pages=2)


if __name__ == "__main__":
  unittest.main()
