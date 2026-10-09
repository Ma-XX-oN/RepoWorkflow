"""Specification tests for external hosted test-result verification."""
from __future__ import annotations

import base64
from copy import deepcopy
import unittest

from repo_workflow.github_evidence import verify_hosted_integration


SHA = "a" * 40
INVOCATION = "b" * 40
REPO = "Ma-XX-oN/RepoWorkflow"
BASE = "https://api.github.com/repos/" + REPO


class HostedIntegrationProviderTests(unittest.TestCase):
  def setUp(self):
    self.record = {
      "providerRunId": 123,
      "providerInvocationSHA": INVOCATION,
      "providerCandidateSHA": SHA,
      "providerStage": "integration-testing",
    }
    self.responses = {
      BASE + "/actions/runs/123": {
        "conclusion": "success", "status": "completed",
        "event": "push", "name": "RepoWorkflow On-Demand CI (candidate)",
        "head_sha": INVOCATION,
      },
      BASE + "/git/commits/" + INVOCATION: {
        "parents": [{"sha": SHA}],
      },
      BASE + "/contents/.ci/run?ref=" + INVOCATION: {
        "encoding": "base64",
        "content": base64.b64encode(
          ("integration-testing " + SHA + "\n").encode(),
        ).decode(),
      },
    }

  def verify(self, record=None, responses=None):
    response_map = responses if responses is not None else self.responses
    return verify_hosted_integration(
      record if record is not None else self.record,
      repo=REPO, read=lambda url: response_map[url],
    )

  def test_actual_completed_run_and_exact_marker_are_accepted(self):
    self.assertTrue(self.verify())

  def test_run_fails_or_is_incomplete(self):
    for field, value in (
      ("conclusion", "failure"), ("status", "queued"),
      ("event", "pull_request"), ("head_sha", SHA),
      ("name", "an unrelated workflow"),
    ):
      with self.subTest(field=field):
        responses = deepcopy(self.responses)
        responses[BASE + "/actions/runs/123"][field] = value
        self.assertFalse(self.verify(responses=responses))

  def test_forged_marker_or_history_does_not_verify(self):
    for marker_text, parent in (
      ("GREEN-testing " + SHA + "\n", SHA),
      ("integration-testing " + INVOCATION + "\n", SHA),
      ("integration-testing " + SHA + " extra\n", SHA),
      ("integration-testing " + SHA + "\n", INVOCATION),
    ):
      with self.subTest(marker=marker_text, parent=parent):
        responses = deepcopy(self.responses)
        responses[BASE + "/git/commits/" + INVOCATION]["parents"] = [
          {"sha": parent},
        ]
        responses[BASE + "/contents/.ci/run?ref=" + INVOCATION][
          "content"
        ] = base64.b64encode(marker_text.encode()).decode()
        self.assertFalse(self.verify(responses=responses))

  def test_missing_provider_fields_and_inaccessible_reads_fail_closed(self):
    for field in ("providerRunId", "providerCandidateSHA",
                  "providerInvocationSHA", "providerStage"):
      with self.subTest(field=field):
        record = dict(self.record)
        record.pop(field)
        self.assertFalse(self.verify(record=record))
    self.assertFalse(self.verify(responses={}))
    self.assertFalse(self.verify(record={**self.record, "providerRunId": True}))


if __name__ == "__main__":
  unittest.main()
