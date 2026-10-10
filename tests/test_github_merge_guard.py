"""Provider contract tests for protected GitHub PR merge acceptance."""
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch

from repo_workflow.github_merge_guard import merge_protected_pr, _github_request
from repo_workflow.pre_merge_gate import PreMergeGateError


REPO = "example/workflow"
BASE = "https://api.github.com/repos/" + REPO
PARENT = "a" * 40
CANDIDATE = "b" * 40
MERGED = "c" * 40


class ProtectedMergeTests(unittest.TestCase):
  def setUp(self):
    self.calls = []
    self.documents = {
      BASE + "/pulls/42": {
        "base": {"ref": "main", "sha": PARENT},
        "head": {"sha": CANDIDATE},
        "state": "open", "draft": False,
      },
      BASE + "/branches/main": {
        "protected": True, "commit": {"sha": PARENT},
      },
      BASE + "/branches/main/protection": {
        "required_status_checks": {
          "strict": True, "contexts": ["repo-workflow/exact-candidate"],
        },
        "enforce_admins": {"enabled": True},
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
      },
    }

  def run_guard(self, documents=None, response=None, evidence=None):
    documents = self.documents if documents is None else documents
    response = {"merged": True, "sha": MERGED} if response is None else response
    def read(url):
      self.calls.append(("read", url))
      return documents[url]
    def merge(url, body):
      self.calls.append(("merge", url, body))
      return response
    def gate():
      self.calls.append(("evidence",))
      if evidence is not None:
        raise evidence
    return merge_protected_pr(
      repo=REPO, pr_number=42,
      candidate_sha=CANDIDATE, recorded_parent_tip=PARENT,
      read=read, merge=merge, evidence_gate=gate,
    )

  def test_exact_candidate_protected_pr_acceptance(self):
    self.assertEqual(self.run_guard(), MERGED)
    self.assertEqual(self.calls[-1], (
      "merge", BASE + "/pulls/42/merge",
      {"sha": CANDIDATE, "merge_method": "merge"},
    ))

  def test_unprotected_stale_and_bypass_paths_never_merge(self):
    cases = (
      (BASE + "/pulls/42", ("head", "sha"), PARENT),
      (BASE + "/pulls/42", ("base", "sha"), CANDIDATE),
      (BASE + "/pulls/42", ("base", "ref"), "issue-42"),
      (BASE + "/pulls/42", ("draft",), True),
      (BASE + "/branches/main", ("protected",), False),
      (BASE + "/branches/main", ("commit", "sha"), CANDIDATE),
      (BASE + "/branches/main/protection",
       ("required_status_checks", "strict"), False),
      (BASE + "/branches/main/protection",
       ("required_status_checks", "contexts"), []),
      (BASE + "/branches/main/protection",
       ("required_status_checks", "contexts"), ["unrelated-check"]),
      (BASE + "/branches/main/protection",
       ("enforce_admins", "enabled"), False),
      (BASE + "/branches/main/protection",
       ("required_pull_request_reviews",), None),
      (BASE + "/branches/main/protection",
       ("allow_force_pushes", "enabled"), True),
      (BASE + "/branches/main/protection",
       ("allow_deletions", "enabled"), True),
    )
    for url, fields, value in cases:
      with self.subTest(url=url, fields=fields):
        docs = deepcopy(self.documents)
        obj = docs[url]
        for key in fields[:-1]:
          obj = obj[key]
        obj[fields[-1]] = value
        self.calls.clear()
        with self.assertRaises(PreMergeGateError):
          self.run_guard(documents=docs)
        self.assertFalse(any(c[0] == "merge" for c in self.calls))

  def test_destination_advanced_during_evidence_gate_refuses_merge(self):
    self.calls.clear()
    docs = deepcopy(self.documents)
    counter = [0]

    def read(url):
      self.calls.append(("read", url))
      if url == BASE + "/branches/main":
        counter[0] += 1
        if counter[0] == 2:
          return {"protected": True, "commit": {"sha": MERGED}}
      return docs[url]

    def merge(url, payload):
      self.calls.append(("merge", url, payload))
      raise AssertionError("stale destination was merged")

    with self.assertRaisesRegex(
      PreMergeGateError, "changed during validation"
    ):
      merge_protected_pr(
        repo=REPO, pr_number=42, candidate_sha=CANDIDATE,
        recorded_parent_tip=PARENT, read=read, merge=merge,
        evidence_gate=lambda: self.calls.append(("evidence",)),
      )
    self.assertEqual(counter[0], 2)
    self.assertFalse(any(c[0] == "merge" for c in self.calls))

  def test_candidate_advanced_during_evidence_gate_refuses_merge(self):
    self.calls.clear()
    docs = deepcopy(self.documents)
    counter = [0]

    def read(url):
      self.calls.append(("read", url))
      if url == BASE + "/pulls/42":
        counter[0] += 1
        if counter[0] == 2:
          result = deepcopy(docs[url])
          result["head"]["sha"] = MERGED
          return result
      return docs[url]

    with self.assertRaisesRegex(
      PreMergeGateError, "changed during validation"
    ):
      merge_protected_pr(
        repo=REPO, pr_number=42, candidate_sha=CANDIDATE,
        recorded_parent_tip=PARENT, read=read,
        merge=lambda url, payload: self.fail("changed head merged"),
        evidence_gate=lambda: self.calls.append(("evidence",)),
      )
    self.assertEqual(counter[0], 2)

  def test_malformed_protection_fails_closed(self):
    for malformed in (None, "not-a-map", {"allow_force_pushes": None}):
      with self.subTest(malformed=malformed):
        docs = deepcopy(self.documents)
        docs[BASE + "/branches/main/protection"] = malformed
        self.calls.clear()
        with self.assertRaises(PreMergeGateError):
          self.run_guard(documents=docs)
        self.assertFalse(any(c[0] == "merge" for c in self.calls))

  def test_inaccessible_protection_fails_closed(self):
    self.calls.clear()
    docs = deepcopy(self.documents)
    del docs[BASE + "/branches/main/protection"]
    with self.assertRaises(PreMergeGateError):
      self.run_guard(documents=docs)
    self.assertFalse(any(c[0] == "merge" for c in self.calls))

  def test_failing_evidence_rejects_before_provider_merge(self):
    self.calls.clear()
    with self.assertRaises(PreMergeGateError):
      self.run_guard(evidence=PreMergeGateError("missing result"))
    self.assertFalse(any(c[0] == "merge" for c in self.calls))

  def test_provider_rejection_and_malformed_result_fail(self):
    for response in ({"merged": False}, {"merged": True}, {"merged": True,
                                                            "sha": "invalid"}):
      with self.subTest(response=response):
        with self.assertRaises(PreMergeGateError):
          self.run_guard(response=response)


class GitHubTransportTests(unittest.TestCase):
  def test_missing_credential_blocks_without_network_call(self):
    with patch.dict("os.environ", {}, clear=True):
      with patch("repo_workflow.github_merge_guard.urlopen") as network:
        with self.assertRaises(ValueError):
          _github_request(BASE + "/pulls/42")
        network.assert_not_called()

  def test_get_and_merge_put_include_authenticated_credential(self):
    class Response:
      def __init__(self, value):
        self.buffer = io.BytesIO(json.dumps(value).encode())
      def __enter__(self):
        return self.buffer
      def __exit__(self, *args):
        self.buffer.close()

    requests = []
    def fake_open(request, timeout):
      requests.append(request)
      return Response({"merged": True, "sha": MERGED})

    with patch.dict("os.environ", {"GITHUB_TOKEN": "dummy-token"}):
      with patch("repo_workflow.github_merge_guard.urlopen",
                 side_effect=fake_open):
        self.assertTrue(_github_request(BASE + "/pulls/42")["merged"])
        self.assertTrue(_github_request(BASE + "/pulls/42/merge",
                                        {"sha": CANDIDATE})["merged"])
    self.assertEqual([req.get_method() for req in requests], ["GET", "PUT"])
    self.assertEqual([req.get_header("Authorization") for req in requests],
                     ["Bearer dummy-token", "Bearer dummy-token"])
    self.assertEqual(json.loads(requests[1].data), {"sha": CANDIDATE})


if __name__ == "__main__":
  unittest.main()
