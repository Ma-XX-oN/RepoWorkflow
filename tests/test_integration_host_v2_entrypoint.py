"""Integration host v2 executable boundary smoke and denial tests."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
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
        "authoritativeRemote": "origin"}},
      verify_remote_scope=lambda root, remote, backend:
        "https://github.com/Org/Repo.git")
    self.assertEqual(result["result"]["sha"], SHA)
    self.assertEqual(calls, [("https://github.com/Org/Repo.git",
                              REF, "b"*40, SHA)])

  def test_cas_rejects_repository_scope_failure_before_git(self):
    request = dict(self.request, operation="ref.cas",
      parameters={"ref": REF, "expected_sha": "b"*40, "sha": SHA})
    attempted = []
    def reject(*args):
      raise IntegrationHostError("provider repository differs")
    with self.assertRaisesRegex(IntegrationHostError, "repository"):
      MOD.process(request, backend_factory=self.factory, verify=self.verify,
        cas_write=lambda *args: attempted.append(args),
        verify_remote_scope=reject,
        config_reader=lambda root: {"repository": {
          "authoritativeRemote": "origin"}})
    self.assertEqual(attempted, [])

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

  def test_destination_snapshot_reads_without_mutation_authority(self):
    request = dict(self.request, operation="destination.read",
                   parameters={"destination": "main"})
    seen = []
    def read(backend, destination):
      seen.append((backend, destination))
      return {"destination": destination, "ref": "refs/heads/main",
              "sha": SHA, "policy_present": True, "policy_text": ""}
    response = MOD.process(
      request, backend_factory=self.factory, destination_read=read)
    self.assertEqual(response["status"], "unchanged")
    self.assertEqual(response["result"]["policy_text"], "")
    self.assertEqual(seen, [(self.backend, "main")])
    self.assertFalse(self.backend.calls)

  def test_retirement_read_is_provider_only(self):
    request = dict(self.request, operation="retirement.read",
                   parameters={"guid": GUID, "ref_kind": "PRELIM"})
    seen = []
    def read(backend, guid, kind):
      seen.append((backend, guid, kind))
      return None
    reply = MOD.process(request, backend_factory=self.factory,
                        retirement_read=read)
    self.assertEqual(reply["result"], {
      "guid": GUID, "ref_kind": "PRELIM", "record": None})
    self.assertEqual(seen, [(self.backend, GUID, "PRELIM")])
    self.assertFalse(self.backend.calls)

  def test_retirement_write_denied_without_independent_verifier(self):
    from tests.test_integration_host_v2 import RETIREMENT
    request = dict(self.request, operation="retirement.record",
                   request_id="retire-1", parameters={
                     "guid": GUID, "ref_kind": "PRELIM",
                     "record": dict(RETIREMENT)})
    called=[]
    with self.assertRaisesRegex(IntegrationHostError, "retirement verifier"):
      MOD.process(request, backend_factory=self.factory, verify=self.verify,
        retirement_write=lambda *args, **kwargs:
          called.append((args, kwargs)))
    self.assertEqual(called, [])

  def test_authorized_retirement_write_is_provider_scoped(self):
    from tests.test_integration_host_v2 import RETIREMENT
    request = dict(self.request, operation="retirement.record",
                   request_id="retire-1", parameters={
                     "guid": GUID, "ref_kind": "PRELIM",
                     "record": dict(RETIREMENT)})
    seen=[]
    def write(backend, record, *, verify_deletion):
      seen.append((backend, record))
      self.assertTrue(verify_deletion(record))
      return "applied", record
    result = MOD.process(
      request, backend_factory=self.factory, verify=self.verify,
      retirement_write=write,
      verify_retirement_evidence=lambda record: True)
    self.assertEqual(result["status"], "applied")
    self.assertEqual(result["result"]["record"], RETIREMENT)
    self.assertEqual(seen, [(self.backend, RETIREMENT)])

  def test_mit_provider_reads_are_independent_of_mutation_authority(self):
    from tests.test_integration_host_v2 import MIT_DEFERRED, MIT_APPROVAL
    for op,kind,key,expected in (
      ("mit.deferred.read","deferred","event",MIT_DEFERRED),
      ("mit.resume.read","resume","authorization",MIT_APPROVAL),
    ):
      seen=[]
      def read(backend, actual_kind, guid, destination):
        seen.append((backend, actual_kind, guid, destination))
        return dict(expected)
      request=dict(self.request,operation=op,parameters={
        "guid":GUID,"destination":"main"})
      result=MOD.process(request,backend_factory=self.factory,
                         mit_read=read)
      self.assertEqual(result["status"],"unchanged")
      self.assertEqual(result["result"][key],expected)
      self.assertEqual(seen,[(self.backend,kind,GUID,"main")])

  def test_mit_provider_write_requires_independent_authority(self):
    from tests.test_integration_host_v2 import MIT_DEFERRED, MIT_APPROVAL
    for op,kind,key,value in (
      ("mit.deferred.record","deferred","event",MIT_DEFERRED),
      ("mit.resume.record","resume","authorization",MIT_APPROVAL),
    ):
      request=dict(self.request,operation=op,parameters={
        "guid":GUID,"destination":"main",key:dict(value)})
      seen=[]
      def write(backend,actual_kind,record,*,verify_evidence):
        seen.append((backend,actual_kind,record))
        if verify_evidence(record) is not True:
          raise IntegrationHostError("trusted verifier denied")
        return "applied",dict(record)
      with self.assertRaisesRegex(IntegrationHostError,"verifier"):
        MOD.process(request,backend_factory=self.factory,verify=self.verify,
                    mit_write=write)
      self.assertFalse(seen)
      result=MOD.process(
        request,backend_factory=self.factory,verify=self.verify,
        mit_write=write,verify_mit_evidence=lambda record:True)
      self.assertEqual(result["status"],"applied")
      self.assertEqual(result["result"][key],value)
      self.assertEqual(seen,[(self.backend,kind,value)])

  def test_mutating_provider_uses_actual_project_checkout(self):
    params = {"destination": "main", "expected_generation": 0,
              "expected_holder": None, "expected_guid": None,
              "holder": "worker-a", "guid": GUID}
    request = dict(self.request, operation="lease.cas", parameters=params)
    observed = {}
    with tempfile.TemporaryDirectory() as temp:
      project = Path(temp).resolve()
      def config_reader(root):
        observed["configured_root"] = root
        return {"repository": {"authoritativeRemote": "origin"}}
      def lease_write(backend, value, root, remote):
        observed["mutation_root"] = root
        observed["remote"] = remote
        return "applied", {"destination": "main", "generation": 1,
                           "holder": "worker-a", "guid": GUID}
      with patch.object(MOD.Path, "cwd", return_value=project):
        result = MOD.process(
          request, backend_factory=self.factory, verify=self.verify,
          config_reader=config_reader, lease_write=lease_write)
      self.assertEqual(result["status"], "applied")
      self.assertEqual(observed["configured_root"], project)
      self.assertEqual(observed["mutation_root"], project)
      self.assertEqual(observed["remote"], "origin")

  def test_lease_cas_rejects_incomplete_identity(self):
    request = dict(self.request, operation="lease.cas", parameters={})
    with self.assertRaises(IntegrationHostError):
      self.call(request=request)
    self.assertFalse(self.backend.calls)

  def test_lease_read_is_provider_scoped_without_mutation(self):
    request = dict(self.request, operation="lease.read",
                   parameters={"destination": "main"})
    seen = []
    def reader(backend, destination):
      seen.append((backend, destination))
      return {"destination": destination, "generation": 0,
              "holder": None, "guid": None}
    result = MOD.process(request, backend_factory=self.factory,
                         lease_read=reader)
    self.assertEqual(result["status"], "unchanged")
    self.assertEqual(result["result"]["generation"], 0)
    self.assertEqual(seen, [(self.backend, "main")])
    self.assertFalse(self.backend.calls)

  def test_lease_cas_requires_trusted_authorization(self):
    params = {"destination": "main", "expected_generation": 0,
              "expected_holder": None, "expected_guid": None,
              "holder": "worker-a", "guid": GUID}
    request = dict(self.request, operation="lease.cas", parameters=params)
    calls = []
    def writer(backend, value, root, remote):
      calls.append((backend, value, remote))
      return "applied", {"destination": "main", "generation": 1,
                         "holder": "worker-a", "guid": GUID}
    with self.assertRaises(IntegrationHostError):
      MOD.process(request, backend_factory=self.factory,
        verify=lambda *args: None, lease_write=writer)
    self.assertEqual(calls, [])
    result = MOD.process(request, backend_factory=self.factory,
      verify=self.verify, lease_write=writer,
      config_reader=lambda root: {"repository": {
        "authoritativeRemote": "origin"}})
    self.assertEqual(result["result"]["generation"], 1)
    self.assertEqual(result["status"], "applied")
    self.assertEqual(calls[0][0], self.backend)
    self.assertEqual(calls[0][2], "origin")


if __name__ == "__main__":
  unittest.main()
