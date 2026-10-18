"""Integration host v2 executable boundary smoke and denial tests."""
import importlib.util
from pathlib import Path
import unittest
from repo_workflow.integration_host_v2 import IntegrationHostError


PATH = Path(__file__).resolve().parents[1] / "adapters" / "repo-host-integration-v2.py"
SPEC = importlib.util.spec_from_file_location("repo_host_integration_v2", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
SHA = "a"*40
GUID = "11111111-1111-4111-8111-111111111111"
REF = "refs/heads/INT-ATTEMPT-issue-123/main-" + GUID


class Backend:
  def __init__(self, repo):
    self.repo = repo
    self.refs = {}
    self.calls = []

  def get(self, route):
    if route.startswith("git/matching-refs"):
      return []
    if route.startswith("git/ref/"):
      ref = "refs/" + route.split("git/ref/", 1)[1]
      if ref in self.refs:
        return {"ref": ref, "object": {"sha": self.refs[ref]}}
      class Missing(Exception):
        code = "not_found"
      raise Missing()
    raise AssertionError("unexpected provider route")

  def post(self, route, payload):
    self.calls.append(route)
    self.refs[payload["ref"]] = payload["sha"]

  def reserve(self, request):
    return True


class V2EntrypointTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend("Org/Repo")
    self.factory = lambda name: self.backend
    self.verify = lambda request, backend: {"grant_id": "trusted"}
    self.request = {
      "schema_version": 2, "repository": "Org/Repo",
      "operation": "ref.create", "request_id": "req-1",
      "parameters": {"ref": REF, "sha": SHA},
    }

  def call(self, request=None, verify=None):
    return MOD.process(self.request if request is None else request,
      backend_factory=self.factory,
      verify=self.verify if verify is None else verify)

  def test_create_result_identity(self):
    result = self.call()
    self.assertEqual(result["schema_version"], 2)
    self.assertEqual(result["status"], "applied")
    self.assertEqual(result["result"]["sha"], SHA)

  def test_trusted_authorization_denial_prevents_write(self):
    def deny(request, backend):
      raise RuntimeError("denied")
    with self.assertRaises(RuntimeError):
      self.call(verify=deny)
    self.assertFalse(self.backend.calls)

  def test_absent_proof_prevents_write(self):
    with self.assertRaisesRegex(IntegrationHostError, "proof missing"):
      self.call(verify=lambda request, backend: None)
    self.assertFalse(self.backend.calls)

  def test_inventory_is_read_only(self):
    request = dict(self.request, operation="refs.list",
      parameters={"prefix": "refs/heads/PRELIM-"})
    result = self.call(request=request)
    self.assertEqual(result["status"], "unchanged")
    self.assertEqual(result["result"], {"refs": {}})
    self.assertFalse(self.backend.calls)

  def test_authorized_ref_cas_uses_configured_remote(self):
    calls = []
    request = dict(self.request, operation="ref.cas",
      parameters={"ref": REF, "expected_sha": "b"*40, "sha": SHA})
    def writer(root, remote, ref, expected, proposed):
      calls.append((remote, ref, expected, proposed))
      return {"ref": ref, "sha": proposed}
    result = MOD.process(request, backend_factory=self.factory,
      verify=self.verify, cas_write=writer,
      config_reader=lambda root: {"repository": {
        "authoritativeRemote": "origin"}})
    self.assertEqual(result["result"]["sha"], SHA)
    self.assertEqual(calls, [("origin", REF, "b"*40, SHA)])

  def test_denied_cas_never_reaches_git(self):
    called = []
    request = dict(self.request, operation="ref.cas",
      parameters={"ref": REF, "expected_sha": "b"*40, "sha": SHA})
    with self.assertRaises(IntegrationHostError):
      MOD.process(request, backend_factory=self.factory,
        verify=lambda req, provider: None,
        cas_write=lambda *args: called.append(args))
    self.assertEqual(called, [])

  def test_terminal_read_is_provider_bound_and_read_only(self):
    request = dict(self.request, operation="attempt.read",
                   parameters={"guid": GUID})
    observed=[]
    def read(backend, guid):
      observed.append((backend, guid))
      return None
    result = MOD.process(request, backend_factory=self.factory,
                         verify=self.verify, terminal_read=read)
    self.assertEqual(result["status"], "unchanged")
    self.assertEqual(result["result"], {"guid": GUID, "record": None})
    self.assertEqual(observed, [(self.backend, GUID)])
    self.assertFalse(self.backend.calls)

  def test_terminal_write_denied_without_trusted_evidence(self):
    from tests.test_integration_host_v2 import TERMINAL
    request = dict(self.request, operation="attempt.record",
                   parameters={"guid": GUID, "record": dict(TERMINAL)})
    attempted=[]
    with self.assertRaisesRegex(IntegrationHostError, "verifier"):
      MOD.process(request, backend_factory=self.factory,
                  verify=self.verify,
                  terminal_write=lambda *args, **kwargs:
                    attempted.append((args, kwargs)))
    self.assertEqual(attempted, [])

  def test_authorized_terminal_write_requires_provider_identity(self):
    from tests.test_integration_host_v2 import TERMINAL
    request = dict(self.request, operation="attempt.record",
                   parameters={"guid": GUID, "record": dict(TERMINAL)})
    observed=[]
    def write(backend, record, *, authorized, verify_evidence):
      observed.append((backend, record, authorized))
      self.assertTrue(verify_evidence(record))
      return "applied", {"guid": GUID, "record": record}
    response = MOD.process(
      request, backend_factory=self.factory, verify=self.verify,
      terminal_write=write, verify_terminal_evidence=lambda record: True)
    self.assertEqual(response["result"]["record"], dict(TERMINAL))
    self.assertEqual(observed,
                     [(self.backend, dict(TERMINAL), True)])

  def test_lease_cas_is_unavailable_not_simulated(self):
    request = dict(self.request, operation="lease.cas", parameters={})
    with self.assertRaises(MOD.IntegrationProviderError):
      self.call(request=request)
    self.assertFalse(self.backend.calls)


if __name__ == "__main__":
  unittest.main()
