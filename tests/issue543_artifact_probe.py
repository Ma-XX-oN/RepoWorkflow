"""Disposable read-only provider artifact authenticity diagnostic."""
import json
import os
import unittest
from io import BytesIO
from zipfile import ZipFile

from repo_workflow.github_artifact import _artifact_bytes, verify_hosted_record
from repo_workflow.github_evidence import github_json, verify_hosted_stage

REPO = "Ma-XX-oN/RepoWorkflow"
RUN = 38115545410
BASE = "https://api.github.com/repos/" + REPO


class ReadOnlyArtifactDiagnostic(unittest.TestCase):
  def test_immutable_provider_readback(self):
    token = os.getenv("GITHUB_TOKEN")
    print("TOKEN_AVAILABLE", bool(token), flush=True)
    run = github_json(BASE + "/actions/runs/" + str(RUN))
    print("RUN", run.get("id"), run.get("status"), run.get("conclusion"), flush=True)
    listing = github_json(BASE + "/actions/runs/" + str(RUN) + "/artifacts?per_page=100")
    artifacts = listing.get("artifacts")
    print("ARTIFACTS", [(a.get("id"), a.get("name"), a.get("expired")) for a in artifacts], flush=True)
    artifact = next(a for a in artifacts if a.get("name") == "provider-result-" + str(RUN))
    content = _artifact_bytes(BASE + "/actions/artifacts/" + str(artifact["id"]) + "/zip")
    with ZipFile(BytesIO(content)) as zipped:
      print("ZIP_FILES", zipped.namelist(), flush=True)
      record = json.loads(zipped.read("testResults-543.jsonl").decode().splitlines()[-1])
    print("RECORD_SHA", record.get("testSHA"), "INVOCATION", record.get("providerInvocationSHA"), flush=True)
    stage_check = verify_hosted_stage(record, repo=REPO, stage="GREEN-testing")
    print("STAGE_VERIFIED", stage_check, flush=True)
    self.assertTrue(verify_hosted_record(record, repo=REPO, stage="GREEN-testing"),
                    "immutable provider artifact should authenticate intact record")


if __name__ == "__main__":
  unittest.main()
