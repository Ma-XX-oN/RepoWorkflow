"""Read-only PRELIM provider inventory; execution refs are immutable."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_host_github_integration import (
  IntegrationProviderError, inventory_ready_refs,
)

SHA = "a"*40
REF = ("refs/heads/PRELIM-issue-123/"
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

  def test_provider_cannot_create_or_mutate_execution_refs(self):
    """Candidate publication uses atomic immutable receipts, not host mutation."""
    from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError
    attempted = []
    host = IntegrationHost("Org/Repo", lambda value: attempted.append(value))
    for operation, parameters in (
        ("ref.create", {"ref":REF,"sha":SHA}),
        ("ref.cas", {"ref":REF,"expected_sha":"b"*40,"sha":SHA})):
      with self.subTest(operation=operation), self.assertRaises(IntegrationHostError):
        host.request(operation, "unsupported-candidate-mutation", parameters)
    self.assertEqual(attempted, [])
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
