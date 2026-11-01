"""#109 real-provider finding: distinct stale INT-CAS requests cannot reconcile."""
import importlib.util
from pathlib import Path
import sys
import unittest

from repo_workflow.integration_host_v2 import IntegrationHostError

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "adapters"
sys.path.insert(0, str(ADAPTERS))
SPEC = importlib.util.spec_from_file_location(
  "rwf109_adapter_under_test", ADAPTERS / "repo-host-integration-v2.py")
assert SPEC and SPEC.loader
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)

GUID = "11111111-1111-4111-8111-111111111111"
REF = "refs/heads/INT-ATTEMPT-issue-109/main-" + GUID
OLD = "a" * 40
NEW = "b" * 40


class Backend:
  repository = "Example/Sandbox"
  def __init__(self):
    self.sha = OLD
    self.reservations = {}

  def get(self, route):
    assert route == "git/ref/" + REF.removeprefix("refs/")
    return {"ref": REF, "object": {"sha": self.sha}}

  def reserve(self, request):
    from adapters.repo_host_github_provider import reservation_digest
    digest = reservation_digest(request)
    key = request["request_id"]
    previous = self.reservations.get(key)
    if previous is not None:
      if previous != digest:
        raise ValueError("request ID reused for changed parameters")
      return False
    self.reservations[key] = digest
    return True


class CasRequestIdentityTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()
    self.calls = []

  def request(self, request_id, *, old=OLD, new=NEW, verify=None, scope=None):
    payload = {
      "schema_version": 2,
      "repository": self.backend.repository,
      "operation": "ref.cas",
      "request_id": request_id,
      "parameters": {"ref": REF, "expected_sha": old, "sha": new},
    }
    def cas_write(root, remote, ref, expected_sha, new_sha):
      self.calls.append((ref, expected_sha, new_sha))
      assert self.backend.sha == expected_sha, "CAS called with stale parent"
      self.backend.sha = new_sha
      return {"ref": ref, "sha": new_sha}
    return ADAPTER.process(
      payload,
      backend_factory=lambda repository: self.backend,
      verify=verify or (lambda request, backend: {"decision": "allow"}),
      config_reader=lambda root: {
        "repository": {"authoritativeRemote": "origin"}},
      verify_remote_scope=scope or (lambda root, remote, backend: "trusted-endpoint"),
      cas_write=cas_write,
    )

  def test_fresh_cas_and_exact_request_replay(self):
    first = self.request("req-1")
    self.assertEqual(first["status"], "applied")
    self.assertEqual(self.backend.sha, NEW)
    second = self.request("req-1")
    self.assertEqual(second["status"], "unchanged")
    self.assertEqual(self.calls, [(REF, OLD, NEW)])

  def test_distinct_stale_request_cannot_claim_other_request_result(self):
    self.request("req-1")
    with self.assertRaisesRegex(IntegrationHostError, "stale"):
      self.request("req-2")
    self.assertEqual(self.backend.sha, NEW)
    self.assertEqual(len(self.calls), 1)

  def test_reserved_request_can_resume_before_remote_cas(self):
    first = self.request("req-1")
    self.assertEqual(first["status"], "applied")
    self.backend.sha = OLD
    result = self.request("req-1")
    self.assertEqual(result["status"], "applied")
    self.assertEqual(self.backend.sha, NEW)

  def test_same_request_id_cannot_be_reused_with_changed_candidate(self):
    self.request("req-1")
    with self.assertRaises(IntegrationHostError):
      self.request("req-1", old="c" * 40, new="d" * 40)

  def test_foreign_remote_denied_before_reservation_or_cas(self):
    def deny_scope(root, remote, backend):
      raise IntegrationHostError("repository scope differs")
    with self.assertRaisesRegex(IntegrationHostError, "repository"):
      self.request("req-bad-remote", scope=deny_scope)
    self.assertEqual(self.backend.reservations, {})
    self.assertEqual(self.backend.sha, OLD)
    self.assertEqual(self.calls, [])

  def test_unauthorized_request_does_not_reserve_or_mutate(self):
    def deny(request, backend):
      raise PermissionError("deny")
    with self.assertRaisesRegex(IntegrationHostError, "authorization"):
      self.request("req-denied", verify=deny)
    self.assertEqual(self.backend.sha, OLD)
    self.assertEqual(self.backend.reservations, {})
    self.assertEqual(self.calls, [])

if __name__ == "__main__":
  unittest.main()
