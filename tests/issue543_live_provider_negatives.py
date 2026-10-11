"""Live provider failure, unavailability, stale and replay acceptance."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from repo_workflow.github_artifact import _artifact_bytes, verify_hosted_record
from repo_workflow.github_evidence import github_json

REPO = "Ma-XX-oN/RepoWorkflow"
API = "https://api.github.com/repos/" + REPO
SUCCESS = 38115866959
FAILED = 38115556576
FAILED_SELECTION = 38115630268
FAILED_PLAN = 38115957182


def record_from_run(run_id):
  listing = github_json(API + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
  artifacts = [x for x in listing.get("artifacts", [])
               if x.get("name") == "provider-result-" + str(run_id)
               and x.get("expired") is False]
  if len(artifacts) != 1:
    return None
  data = _artifact_bytes(API + "/actions/artifacts/"
                         + str(artifacts[0]["id"]) + "/zip")
  with ZipFile(BytesIO(data)) as z:
    lines = z.read("testResults-543.jsonl").decode("utf-8").splitlines()
  records = [json.loads(line) for line in lines]
  return next((row for row in records if row.get("providerRunId") == run_id), None)


class LiveProviderNegativeOutcomeMatrix(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.good = record_from_run(SUCCESS)
    cls.incomplete = record_from_run(FAILED)
    cls.invalid_selection = record_from_run(FAILED_SELECTION)
    if cls.good is None or cls.incomplete is None:
      raise AssertionError("required independently persisted provider evidence absent")

  def accepted(self, record):
    return verify_hosted_record(record, repo=REPO, stage="GREEN-testing")

  def test_authentic_completed_success_only(self):
    self.assertTrue(self.accepted(self.good))

  def test_real_incomplete_red_is_not_an_accepted_pass(self):
    self.assertEqual(self.incomplete.get("result"), "incomplete")
    self.assertEqual(self.incomplete.get("redStatus"), "INCOMPLETE")
    self.assertFalse(self.accepted(self.incomplete))

  def test_real_failed_selection_is_not_accepted(self):
    run = github_json(API + "/actions/runs/" + str(FAILED_SELECTION))
    self.assertEqual(run["conclusion"], "failure")
    if self.invalid_selection is not None:
      self.assertFalse(self.accepted(self.invalid_selection))

  def test_real_failed_plan_has_no_provider_result(self):
    run = github_json(API + "/actions/runs/" + str(FAILED_PLAN))
    self.assertEqual(run["conclusion"], "failure")
    self.assertIsNone(record_from_run(FAILED_PLAN))

  def test_real_nonexistent_provider_run_rejected(self):
    forged = deepcopy(self.good)
    forged["providerRunId"] = 999999999999
    self.assertFalse(self.accepted(forged))

  def test_real_run_stale_invocation_rejected(self):
    forged = deepcopy(self.good)
    forged["providerInvocationSHA"] = "f" * 40
    self.assertFalse(self.accepted(forged))

  def test_real_run_stale_source_rejected(self):
    forged = deepcopy(self.good)
    forged["providerCandidateSHA"] = "e" * 40
    forged["testSHA"] = "e" * 40
    self.assertFalse(self.accepted(forged))

  def test_real_run_replayed_group_claim_rejected(self):
    forged = deepcopy(self.good)
    forged["groups"] = [{"group": "issue-543-never-ran", "exit_code": 0}]
    self.assertFalse(self.accepted(forged))

  def test_real_run_replayed_stage_rejected(self):
    forged = deepcopy(self.good)
    forged["kind"] = "integration"
    forged["providerStage"] = "integration-testing"
    self.assertFalse(self.accepted(forged))

  def test_real_run_changed_catalogue_hash_rejected(self):
    forged = deepcopy(self.good)
    forged["catalogueSHA256"] = "a" * 64
    self.assertFalse(self.accepted(forged))

  def test_real_run_changed_reuse_lineage_rejected(self):
    forged = deepcopy(self.good)
    forged["reusedFromRunId"] = FAILED
    self.assertFalse(self.accepted(forged))

  def test_missing_provider_data_fails_closed(self):
    forged = deepcopy(self.good)
    self.assertFalse(verify_hosted_record(
      forged, repo=REPO, stage="GREEN-testing",
      read=lambda _: (_ for _ in ()).throw(ValueError("provider unavailable")),
    ))


if __name__ == "__main__":
  unittest.main()
