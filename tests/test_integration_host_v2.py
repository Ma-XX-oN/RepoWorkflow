"""Protocol-negative tests for a separate versioned host extension."""
import unittest
from repo_workflow.integration_host_v2 import IntegrationHost, IntegrationHostError

GUID = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/INT-ATTEMPT-issue-123/main-{GUID}"
SHA = "a"*40


def accepted(request):
  return dict(schema_version=2, repository=request["repository"],
              operation=request["operation"], request_id=request["request_id"],
              status="applied", result={"ok": True})


class IntegrationHostV2Tests(unittest.TestCase):
  def setUp(self):
    self.host = IntegrationHost("Org/Repo", accepted)

  def test_v2_request_echo(self):
    result = self.host.request("ref.create", "request-1", {"ref": REF, "sha": SHA})
    self.assertTrue(result["ok"])

  def test_published_prelim_mutation_forbidden(self):
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "request-1", {
        "ref": f"refs/heads/PRELIM-issue-123/main-{GUID}", "sha": SHA})

  def test_only_reserved_prelim_inventory(self):
    self.assertTrue(self.host.request("refs.list", "list-1", {
      "prefix": "refs/heads/PRELIM-"})["ok"])
    with self.assertRaises(IntegrationHostError):
      self.host.request("refs.list", "list-2", {"prefix": "refs/heads/main"})

  def test_stale_or_malformed_lease_request(self):
    params = dict(destination="main", expected_generation=0,
                  expected_holder=None, expected_guid=None,
                  holder="worker-A", guid=GUID)
    self.assertTrue(self.host.request("lease.cas", "claim-1", params)["ok"])
    for change in ({"expected_generation": -1}, {"expected_generation": True},
                   {"holder": ""}, {"unexpected": "field"}):
      with self.subTest(change=change):
        with self.assertRaises(IntegrationHostError):
          self.host.request("lease.cas", "claim-2", dict(params, **change))

  def test_stale_echo_rejected(self):
    def wrong(request):
      reply = accepted(request)
      reply["request_id"] = "other"
      return reply
    self.host = IntegrationHost("Org/Repo", wrong)
    with self.assertRaisesRegex(IntegrationHostError, "mismatch"):
      self.host.request("ref.create", "request-1", {"ref": REF, "sha": SHA})

  def test_transport_unknown_is_not_success(self):
    self.host = IntegrationHost("Org/Repo", lambda request: 1/0)
    with self.assertRaisesRegex(IntegrationHostError, "UNKNOWN"):
      self.host.request("ref.create", "request-1", {"ref": REF, "sha": SHA})

  def test_v1_response_not_accepted(self):
    def legacy(request):
      response = accepted(request)
      response["schema_version"] = 1
      return response
    self.host = IntegrationHost("Org/Repo", legacy)
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.create", "request-1", {"ref": REF, "sha": SHA})

  def test_invalid_sha_rejected_before_transport(self):
    called = []
    self.host = IntegrationHost("Org/Repo", lambda request: called.append(request))
    with self.assertRaises(IntegrationHostError):
      self.host.request("ref.cas", "r-1", {
        "ref": REF, "expected_sha": "invalid", "sha": SHA})
    self.assertFalse(called)

  def test_attempt_result_requires_pinned_candidate(self):
    self.assertTrue(self.host.request("attempt.record", "r-1", {
      "guid": GUID, "status": "integrated", "sha": SHA})["ok"])
    with self.assertRaises(IntegrationHostError):
      self.host.request("attempt.record", "r-2", {
        "guid": GUID, "status": "timeout-as-fail", "sha": SHA})


if __name__ == "__main__":
  unittest.main()
