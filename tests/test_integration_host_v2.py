"""Negative tests for the separate versioned integration-host contract."""
import unittest
from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError

GUID = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/INT-ATTEMPT-issue-123/main-{GUID}"
SHA = "a"*40
TERMINAL = {
  "repository": "Org/Repo", "guid": GUID, "status": "integrated",
  "prelim_ref": f"refs/heads/PRELIM-issue-123/main-{GUID}",
  "prelim_sha": "b"*40,
  "int_attempt_ref": REF, "accepted_sha": SHA,
  "destination_ref": "refs/heads/main",
  "expected_destination_sha": "c"*40,
  "observed_destination_sha": "d"*40, "landed_sha": "d"*40,
  "provider_operation_id": "merge-op-123", "umbrella": "issue-123",
  "integration_id": "integration-123",
  "terminal_evidence_ref": "terminal-123",
}


RETIREMENT = {
  "repository": "Org/Repo", "guid": GUID, "ref_kind": "PRELIM",
  "retired_ref": TERMINAL["prelim_ref"],
  "expected_sha": TERMINAL["prelim_sha"],
  "operation_id": "retire-1",
  "terminal_evidence_ref": TERMINAL["terminal_evidence_ref"],
  "destination_ref": TERMINAL["destination_ref"],
  "landed_sha": TERMINAL["landed_sha"],
  "outcome": "retired",
}


def good(request):
  p = request["parameters"]
  result = {
    "destination.read": lambda: {
      "destination": p["destination"],
      "ref": "refs/heads/" + p["destination"], "sha": SHA,
      "policy_present": False, "policy_text": None},
    "refs.list": lambda: {"refs": {}},
    "ref.create": lambda: {"ref": p["ref"], "sha": p["sha"]},
    "ref.cas": lambda: {"ref": p["ref"], "sha": p["sha"]},
    "lease.read": lambda: {
      "destination": p["destination"], "generation": 0,
      "guid": None, "holder": None},
    "lease.cas": lambda: {
      "destination": p["destination"], "generation": p["expected_generation"]+1,
      "guid": p["guid"], "holder": p["holder"]},
    "attempt.read": lambda: {"guid": p["guid"], "record": None},
    "attempt.record": lambda: {
      "guid": p["guid"], "record": p["record"]},
    "retirement.read": lambda: {
      "guid": p["guid"], "ref_kind": p["ref_kind"], "record": None},
    "retirement.record": lambda: {
      "guid": p["guid"], "ref_kind": p["ref_kind"],
      "record": p["record"]},
  }[request["operation"]]()
  return dict(schema_version=2, repository=request["repository"],
              operation=request["operation"], request_id=request["request_id"],
              status=("unchanged" if request["operation"] in {
                "destination.read", "refs.list", "lease.read",
                "attempt.read", "retirement.read"} else "applied"),
              result=result)


class IntegrationHostV2Tests(unittest.TestCase):
  def setUp(self):
    self.host = IntegrationHost("Org/Repo", good)

  def test_echo(self):
    result = self.host.request("ref.create", "req-1", {"ref": REF, "sha": SHA})
    self.assertEqual(result["sha"], SHA)

  def test_prelim_mutation_rejected(self):
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "req-1", {
        "ref": REF.replace("INT-ATTEMPT", "PRELIM"), "sha": SHA})

  def test_exact_destination_policy_snapshot_contract(self):
    result=self.host.request("destination.read","read-dest-1",
                             {"destination":"main"})
    self.assertEqual(result["sha"],SHA)
    self.assertFalse(result["policy_present"])
    self.assertIsNone(result["policy_text"])

  def test_read_only_host_must_not_report_applied_mutation(self):
    def forged(request):
      reply=good(request)
      reply["status"]="applied"
      return reply
    host=IntegrationHost("Org/Repo",forged)
    with self.assertRaisesRegex(IntegrationHostError, "read-only"):
      host.request("destination.read","read-dest-fake",
                   {"destination":"main"})

  def test_forged_destination_policy_result_rejected(self):
    def invalid(request):
      reply=good(request)
      reply["result"]["policy_present"]=True
      return reply
    host=IntegrationHost("Org/Repo",invalid)
    with self.assertRaises(IntegrationHostError):
      host.request("destination.read","read-dest-2",
                   {"destination":"main"})

  def test_generic_umbrella_int_attempt(self):
    ref=f"refs/heads/INT-ATTEMPT-team-alpha/main-{GUID}"
    result=self.host.request("ref.create","generic-1",{"ref":ref,"sha":SHA})
    self.assertEqual(result["ref"],ref)

  def test_inventory_prefix_only(self):
    self.assertEqual(self.host.request("refs.list", "list-1", {
      "prefix": "refs/heads/PRELIM-"})["refs"], {})
    with self.assertRaises(IntegrationHostError):
      self.host.request("refs.list", "list-2", {"prefix": "refs/heads/main"})

  def test_malformed_lease_request(self):
    params = dict(destination="main", expected_generation=0,
                  expected_holder=None, expected_guid=None,
                  holder="worker-A", guid=GUID)
    self.assertEqual(self.host.request(
      "lease.cas", "claim-1", params)["generation"], 1)
    for update in ({"expected_generation": -1}, {"expected_generation": True},
                   {"holder": ""}, {"expected_guid": GUID},
                   {"unexpected": "value"}):
      with self.subTest(update=update):
        with self.assertRaises(IntegrationHostError):
          self.host.request("lease.cas", "claim-2", dict(params, **update))

  def test_lease_result_must_match_requested_owner_and_generation(self):
    params = dict(destination="main", expected_generation=3,
                  expected_holder=None, expected_guid=None,
                  holder="worker-A", guid=GUID)
    def wrong(request):
      reply = good(request)
      reply["result"]["generation"] = 3
      return reply
    self.host = IntegrationHost("Org/Repo", wrong)
    with self.assertRaisesRegex(IntegrationHostError, "result"):
      self.host.request("lease.cas", "claim-1", params)

  def test_lease_result_wrong_holder_is_not_accepted(self):
    params = dict(destination="main", expected_generation=0,
                  expected_holder=None, expected_guid=None,
                  holder="worker-A", guid=GUID)
    def wrong(request):
      reply = good(request)
      reply["result"]["holder"] = "worker-B"
      return reply
    self.host = IntegrationHost("Org/Repo", wrong)
    with self.assertRaises(IntegrationHostError):
      self.host.request("lease.cas", "claim-2", params)

  def test_stale_echo_rejected(self):
    def wrong(request):
      result = good(request)
      result["request_id"] = "wrong"
      return result
    self.host = IntegrationHost("Org/Repo", wrong)
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "req-1", {"ref": REF, "sha": SHA})

  def test_transport_unknown(self):
    self.host = IntegrationHost("Org/Repo", lambda request: 1/0)
    with self.assertRaisesRegex(IntegrationHostError, "UNKNOWN"):
      self.host.request("ref.create", "req-1", {"ref": REF, "sha": SHA})

  def test_v1_response_rejected(self):
    def old(request):
      result = good(request)
      result["schema_version"] = 1
      return result
    self.host = IntegrationHost("Org/Repo", old)
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "req-1", {"ref": REF, "sha": SHA})

  def test_invalid_sha_rejected_without_transport(self):
    called = []
    self.host = IntegrationHost("Org/Repo", lambda request: called.append(request))
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.cas", "req-1", {
        "ref": REF, "expected_sha": "bad", "sha": SHA})
    self.assertFalse(called)

  def test_terminal_pin(self):
    result=self.host.request("attempt.record", "req-1", {
      "guid": GUID, "record": dict(TERMINAL)})
    self.assertEqual(result["record"]["landed_sha"], "d"*40)
    with self.assertRaises(IntegrationHostError):
      self.host.request("attempt.record", "req-2", {
        "guid": GUID, "record": dict(TERMINAL,status="timeout-as-fail")})

  def test_terminal_rejects_foreign_repository(self):
    called=[]
    self.host=IntegrationHost("Org/Repo",
      lambda request:called.append(request))
    with self.assertRaises(IntegrationHostError):
      self.host.request("attempt.record", "req-3", {
        "guid":GUID,"record":dict(TERMINAL,repository="Other/Repo")})
    self.assertEqual(called,[])

  def test_terminal_rejects_missing_provenance(self):
    for field in ("prelim_ref", "prelim_sha", "int_attempt_ref",
                  "accepted_sha", "destination_ref", "landed_sha",
                  "integration_id", "provider_operation_id",
                  "umbrella", "observed_destination_sha",
                  "terminal_evidence_ref"):
      value=dict(TERMINAL)
      value.pop(field)
      with self.subTest(field=field):
        with self.assertRaises(IntegrationHostError):
          self.host.request("attempt.record", "req-4", {
            "guid":GUID,"record":value})

  def test_nonlanded_terminal_cannot_assert_landed_sha(self):
    with self.assertRaises(IntegrationHostError):
      self.host.request("attempt.record", "req-5", {
        "guid":GUID,
        "record":dict(TERMINAL,status="failed")})
    result=self.host.request("attempt.record", "req-6", {
      "guid":GUID,
      "record":dict(TERMINAL,status="failed",landed_sha=None)})
    self.assertIsNone(result["record"]["landed_sha"])

  def test_terminal_rejects_cross_umbrella_and_destination(self):
    bad_records=(
      dict(TERMINAL,int_attempt_ref=
        f"refs/heads/INT-ATTEMPT-other/main-{GUID}"),
      dict(TERMINAL,destination_ref="refs/heads/issue-999"),
      dict(TERMINAL,prelim_ref=
        f"refs/heads/PRELIM-issue-123/other-{GUID}"),
      dict(TERMINAL,umbrella="issue-999"),
      dict(TERMINAL,provider_operation_id=""),
      dict(TERMINAL,observed_destination_sha="invalid"),
    )
    for record in bad_records:
      with self.subTest(record=record):
        with self.assertRaises(IntegrationHostError):
          self.host.request("attempt.record","scope-neg",{
            "guid":GUID,"record":record})

  def test_retirement_record_bound_to_request_and_repository(self):
    p={"guid": GUID, "ref_kind": "PRELIM", "record": dict(RETIREMENT)}
    value=self.host.request("retirement.record", "retire-1", p)
    self.assertEqual(value["record"], RETIREMENT)
    for change in (
      {"operation_id": "different"},
      {"repository": "Other/Repo"},
      {"guid": "22222222-2222-4222-8222-222222222222"},
      {"retired_ref": TERMINAL["int_attempt_ref"]},
      {"outcome": "unknown"},
      {"ref_kind": "bad"},
    ):
      with self.subTest(change=change):
        with self.assertRaises(IntegrationHostError):
          self.host.request("retirement.record", "retire-1", {
            "guid": GUID, "ref_kind": "PRELIM",
            "record": dict(RETIREMENT, **change)})
    with self.assertRaises(IntegrationHostError):
      self.host.request("retirement.record", "retire-1", {
        "guid":GUID, "ref_kind":"PRELIM", "record":"not-a-dict"})

  def test_retirement_read_absence_is_not_success(self):
    result=self.host.request("retirement.read", "audit-read", {
      "guid": GUID, "ref_kind": "INT-ATTEMPT"})
    self.assertIsNone(result["record"])

  def test_retirement_read_rejects_forged_repository(self):
    def foreign(request):
      reply=good(request)
      reply["result"]["record"]=dict(RETIREMENT,repository="Other/Repo")
      return reply
    host=IntegrationHost("Org/Repo", foreign)
    with self.assertRaises(IntegrationHostError):
      host.request("retirement.read","forged-audit",{
        "guid":GUID,"ref_kind":"PRELIM"})

  def test_readback_rejects_foreign_provider_terminal(self):
    def foreign(request):
      reply=good(request)
      reply["result"]["record"]=dict(TERMINAL,repository="Other/Repo")
      return reply
    self.host=IntegrationHost("Org/Repo", foreign)
    with self.assertRaises(IntegrationHostError):
      self.host.request("attempt.read", "req-7", {"guid":GUID})

  def test_wrong_result_candidate_denied(self):
    def fake(request):
      result = good(request)
      result["result"]["sha"] = "b"*40
      return result
    self.host = IntegrationHost("Org/Repo", fake)
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "req-1", {"ref": REF, "sha": SHA})

  def test_wrong_result_shape_denied(self):
    def fake(request):
      result = good(request)
      result["result"]["unexpected"] = "x"
      return result
    self.host = IntegrationHost("Org/Repo", fake)
    with self.assertRaises(IntegrationHostError):
      self.host.request("refs.list", "req-1", {"prefix": "refs/heads/PRELIM-"})


if __name__ == "__main__":
  unittest.main()
