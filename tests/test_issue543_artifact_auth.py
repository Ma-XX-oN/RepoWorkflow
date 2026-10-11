"""Immutable GitHub Actions artifact authentication rejects fabricated PASSes."""
from copy import deepcopy
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from repo_workflow.github_artifact import verify_hosted_record
from tests.test_issue543_hosted_lineage import (
  BASE, CANDIDATE, REPO, RETRY, VerifiedRetryLineageTests,
)


def archive(*records):
  buffer = BytesIO()
  with ZipFile(buffer, "w") as zipped:
    zipped.writestr(
      "testResults-543.jsonl",
      "".join(json.dumps(row) + "\n" for row in records),
    )
  return buffer.getvalue()


class ImmutableProviderArtifactTests(unittest.TestCase):
  def setUp(self):
    fixture = VerifiedRetryLineageTests()
    fixture.setUp()
    self.responses = fixture.responses
    self.record = {
      **fixture.record,
      "branch": "issue-543-auth-test", "kind": "GREEN",
      "testSHA": CANDIDATE, "result": "succeeded",
      "runner": "github-actions", "reusable": True,
      "uncommittedChanges": [], "headChangedDuringTest": False,
      "catalogueSHA256": "e" * 64,
      "groups": [{"group": "issue-543-real-group", "exit_code": 0}],
    }
    self.url = BASE + "/actions/runs/123/artifacts?per_page=100"
    self.responses[self.url] = {
      "total_count": 1,
      "artifacts": [{
        "id": 444, "name": "provider-result-123",
        "expired": False, "size_in_bytes": 1024,
        "workflow_run": {"id": 123, "head_sha": RETRY},
      }],
    }
    self.bytes = archive(self.record)

  def check(self, record=None, responses=None, zipped=None):
    source = responses if responses is not None else self.responses
    return verify_hosted_record(
      record if record is not None else self.record,
      repo=REPO, stage="GREEN-testing",
      read=lambda url: source[url],
      download=lambda _: self.bytes if zipped is None else zipped,
    )

  def test_immutable_artifact_exact_record_is_accepted(self):
    self.assertTrue(self.check())

  def test_forged_group_with_real_run_id_is_rejected(self):
    forged = deepcopy(self.record)
    forged["groups"] = [{"group": "issue-543-never-tested", "exit_code": 0}]
    self.assertFalse(self.check(forged))

  def test_forged_catalogue_reuse_and_platform_rejected(self):
    for field, value in (
      ("catalogueSHA256", "f" * 64),
      ("reusedFromRunId", 55),
      ("platform", {"os": "Windows"}),
    ):
      with self.subTest(field=field):
        forged = deepcopy(self.record)
        forged[field] = value
        self.assertFalse(self.check(forged))

  def test_missing_expired_duplicate_artifacts_rejected(self):
    one = self.responses[self.url]["artifacts"][0]
    variants = ([], [{**one, "expired": True}], [one, one])
    for listing in variants:
      with self.subTest(listing=listing):
        responses = deepcopy(self.responses)
        responses[self.url]["artifacts"] = listing
        self.assertFalse(self.check(responses=responses))

  def test_truncated_or_nonzip_artifact_rejected(self):
    for raw in (b"", b"not a zip", self.bytes[:18]):
      with self.subTest(length=len(raw)):
        self.assertFalse(self.check(zipped=raw))

  def test_invalid_trailing_record_rejects_entire_artifact(self):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zipped:
      zipped.writestr(
        "testResults-543.jsonl", json.dumps(self.record) + "\n{bad\n",
      )
    self.assertFalse(self.check(zipped=buffer.getvalue()))

  def test_provider_unavailable_rejected(self):
    responses = deepcopy(self.responses)
    del responses[self.url]
    self.assertFalse(self.check(responses=responses))

  def test_missing_required_provider_field_rejected(self):
    for key in (
      "providerRunId", "providerInvocationSHA", "providerCandidateSHA",
    ):
      with self.subTest(key=key):
        forged = deepcopy(self.record)
        del forged[key]
        self.assertFalse(self.check(forged))


if __name__ == "__main__":
  unittest.main()
