"""Specification tests for external hosted test-result verification."""
from __future__ import annotations

import base64
from copy import deepcopy
import unittest

from repo_workflow.github_evidence import (
  verify_hosted_integration, verify_hosted_stage,
)


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
        "id": 123, "conclusion": "success", "status": "completed",
        "event": "push", "name": "RepoWorkflow On-Demand CI (candidate)",
        "head_sha": INVOCATION,
      },
      BASE + "/git/commits/" + INVOCATION: {
        "parents": [{"sha": SHA}],
      },
      BASE + "/actions/runs/123/jobs?per_page=100": {
        "total_count": 11,
        "jobs": [
          {"name": name, "conclusion": "success"}
          for name in (
            "plan", "validate",
            *(
              group + " (" + system + ")"
              for group in (
                "argv-limits", "graph-renderer-platform",
                "ticket-merge-platform",
              )
              for system in ("ubuntu-latest", "windows-latest", "macos-latest")
            ),
          )
        ],
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
      ("id", 999), ("conclusion", "failure"), ("status", "queued"),
      ("event", "pull_request"), ("head_sha", SHA),
      ("name", "an unrelated workflow"),
    ):
      with self.subTest(field=field):
        responses = deepcopy(self.responses)
        responses[BASE + "/actions/runs/123"][field] = value
        self.assertFalse(self.verify(responses=responses))

  def test_green_and_temporary_provider_are_verifiable_without_matrix(self):
    jobs_url = BASE + "/actions/runs/123/jobs?per_page=100"
    marker_url = BASE + "/contents/.ci/run?ref=" + INVOCATION
    for stage in ("GREEN-testing", "temp-testing", "regression-testing"):
      with self.subTest(stage=stage):
        record = {**self.record, "providerStage": stage}
        responses = deepcopy(self.responses)
        responses[jobs_url]["jobs"] = [
          {"name": "plan", "conclusion": "success"},
          {"name": "validate", "conclusion": "success"},
        ]
        responses[jobs_url]["total_count"] = 2
        responses[marker_url]["content"] = base64.b64encode(
          (stage + " " + SHA + "\n").encode(),
        ).decode()
        self.assertTrue(verify_hosted_stage(
          record, repo=REPO, stage=stage,
          read=lambda url: responses[url],
        ))
        self.assertFalse(verify_hosted_integration(
          record, repo=REPO, read=lambda url: responses[url],
        ))
        responses[jobs_url]["jobs"][1]["conclusion"] = "failure"
        self.assertFalse(verify_hosted_stage(
          record, repo=REPO, stage=stage,
          read=lambda url: responses[url],
        ))

  def test_missing_skipped_or_duplicate_matrix_job_fails(self):
    jobs_url = BASE + "/actions/runs/123/jobs?per_page=100"
    for field in ("validate", "argv-limits (windows-latest)",
                  "graph-renderer-platform (macos-latest)"):
      with self.subTest(job=field):
        changed = deepcopy(self.responses)
        for job in changed[jobs_url]["jobs"]:
          if job["name"] == field:
            job["conclusion"] = "skipped"
        self.assertFalse(self.verify(responses=changed))
    changed = deepcopy(self.responses)
    changed[jobs_url]["jobs"] = changed[jobs_url]["jobs"][:-1]
    changed[jobs_url]["total_count"] -= 1
    self.assertFalse(self.verify(responses=changed))
    changed = deepcopy(self.responses)
    changed[jobs_url]["jobs"][1]["name"] = "plan"
    self.assertFalse(self.verify(responses=changed))

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

  def test_github_line_wrapped_base64_marker_is_accepted(self):
    responses = deepcopy(self.responses)
    url = BASE + "/contents/.ci/run?ref=" + INVOCATION
    raw = responses[url]["content"]
    responses[url]["content"] = raw[:20] + "\n" + raw[20:] + "\n"
    self.assertTrue(self.verify(responses=responses))

  def test_marker_base64_rejects_non_alphabet_bytes(self):
    responses = deepcopy(self.responses)
    url = BASE + "/contents/.ci/run?ref=" + INVOCATION
    responses[url]["content"] += "!!"
    self.assertFalse(self.verify(responses=responses))

  def test_missing_provider_fields_and_inaccessible_reads_fail_closed(self):
    for field in ("providerRunId", "providerCandidateSHA",
                  "providerInvocationSHA", "providerStage"):
      with self.subTest(field=field):
        record = dict(self.record)
        record.pop(field)
        self.assertFalse(self.verify(record=record))
    self.assertFalse(self.verify(responses={}))
    broken = deepcopy(self.responses)
    broken[BASE + "/actions/runs/123"] = None
    self.assertFalse(self.verify(responses=broken))
    self.assertFalse(self.verify(record={**self.record, "providerRunId": True}))


if __name__ == "__main__":
  unittest.main()
