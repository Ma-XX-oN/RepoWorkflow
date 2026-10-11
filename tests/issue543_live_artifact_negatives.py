"""Live read-only negative acceptance against genuine GitHub Actions artifacts."""
from copy import deepcopy
from io import BytesIO
import json
import os
import unittest
from zipfile import ZipFile

from repo_workflow.github_artifact import _artifact_bytes, verify_hosted_record
from repo_workflow.github_evidence import github_json

REPO = "Ma-XX-oN/RepoWorkflow"
API = "https://api.github.com/repos/" + REPO
GOOD_RUN = 38115545410
FAILED_RUN = 38115556576


def immutable_record(run_id):
  listing = github_json(API + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
  exact = [a for a in listing["artifacts"]
           if a["name"] == "provider-result-" + str(run_id)]
  if len(exact) != 1:
    raise AssertionError("real provider artifact missing")
  content = _artifact_bytes(
    API + "/actions/artifacts/" + str(exact[0]["id"]) + "/zip")
  with ZipFile(BytesIO(content)) as archive:
    return json.loads(archive.read("testResults-543.jsonl").decode().splitlines()[-1])


class LiveArtifactNegativeTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not os.getenv("GITHUB_TOKEN"):
      raise AssertionError("live provider token unavailable")

  def test_real_success_artifact_authenticates(self):
    record = immutable_record(GOOD_RUN)
    self.assertTrue(verify_hosted_record(record, repo=REPO, stage="GREEN-testing"))

  def test_forged_group_reusing_successful_run_is_rejected(self):
    record = immutable_record(GOOD_RUN)
    fake = deepcopy(record)
    fake["groups"] = [{"group": "issue-543-forged-unexecuted", "exit_code": 0}]
    self.assertFalse(verify_hosted_record(fake, repo=REPO, stage="GREEN-testing"))

  def test_real_failed_provider_run_cannot_impersonate_success(self):
    record = immutable_record(FAILED_RUN)
    fake = deepcopy(record)
    fake["result"] = "succeeded"
    fake["kind"] = "GREEN"
    fake["providerStage"] = "GREEN-testing"
    fake["groups"] = [{"group": "issue-543-forged-unexecuted", "exit_code": 0}]
    self.assertFalse(verify_hosted_record(fake, repo=REPO, stage="GREEN-testing"))

  def test_missing_provider_run_fails_closed(self):
    record = immutable_record(GOOD_RUN)
    fake = deepcopy(record)
    fake["providerRunId"] = 999999999999
    self.assertFalse(verify_hosted_record(fake, repo=REPO, stage="GREEN-testing"))


if __name__ == "__main__":
  unittest.main()
