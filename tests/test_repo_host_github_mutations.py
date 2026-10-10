from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters"))
from repo_host_github_mutations import apply
from repo_host_github_provider import ProviderError


SHA = "a" * 40
OTHER = "b" * 40


def req(operation, parameters, request_id="once"):
  return {
    "schema_version": 1, "operation": operation,
    "repository": "owner/repo", "request_id": request_id,
    "parameters": parameters,
  }


class FakeGitHub:
  def __init__(self):
    self.issue_state = {"number": 3, "title": "Old", "state": "open"}
    self.comments = []
    self.pr = {
      "number": 7, "head": {"sha": SHA, "ref": "work"},
      "base": {"sha": OTHER, "ref": "main"}, "state": "open",
      "draft": True, "title": "Original", "body": "",
    }
    self.refs = {"refs/heads/work": SHA, "refs/heads/main": OTHER}
    self.reserved = set()
    self.writes = []

  def identity(self):
    return {"login": "trusted"}

  def reserve(self, request):
    key = (
      request["repository"], request["operation"], request["request_id"]
    )
    if key in self.reserved:
      return False
    self.reserved.add(key)
    return True

  def issue(self, number):
    if number != 3:
      raise ProviderError("not_found", "missing issue")
    return dict(self.issue_state)

  def pull(self, number):
    if number != 7:
      raise ProviderError("not_found", "missing PR")
    return dict(self.pr)

  def get(self, path):
    if path.startswith("issues/3/comments?"):
      return list(self.comments)
    if path.startswith("pulls?"):
      return [dict(self.pr)] if self.pr["body"] else []
    if path.startswith("git/ref/heads/"):
      name = path.removeprefix("git/ref/heads/")
      ref = "refs/heads/" + name
      return {"ref": ref, "object": {
        "sha": self.refs[ref], "type": "commit",
      }}
    raise AssertionError("unexpected provider GET " + path)

  def patch(self, path, body):
    self.writes.append(("PATCH", path, dict(body)))
    if path == "issues/3":
      self.issue_state.update(body)
      return dict(self.issue_state)
    if path == "pulls/7":
      self.pr.update({k: v for k, v in body.items() if k != "base"})
      if "base" in body:
        self.pr["base"] = {
          "ref": body["base"], "sha": self.refs["refs/heads/main"],
        }
      return dict(self.pr)
    raise AssertionError("unexpected patch")

  def post(self, path, body):
    self.writes.append(("POST", path, dict(body)))
    if path == "issues/3/comments":
      item = {"id": 123, **body}
      self.comments.append(item)
      return item
    if path == "pulls":
      self.pr = {
        "number": 7, "head": {"sha": SHA, "ref": "work"},
        "base": {"sha": OTHER, "ref": "main"},
        "state": "open", **body,
      }
      return dict(self.pr)
    raise AssertionError("unexpected post")


class OrdinaryMutationTests(unittest.TestCase):

  def setUp(self):
    self.backend = FakeGitHub()
    self.authorize = patch(
      "repo_host_github_mutations.authorize",
      return_value={"decision": "allow"},
    )
    self.authorize.start()
    self.addCleanup(self.authorize.stop)

  def test_issue_update_and_idempotent_retry(self):
    request = req("issue.update", {"number": 3, "title": "Changed"})
    self.assertEqual(apply(request, self.backend)[0], "applied")
    self.assertEqual(apply(request, self.backend)[0], "unchanged")
    self.assertEqual(len(self.backend.writes), 1)
    self.assertEqual(self.backend.issue_state["title"], "Changed")

  def test_issue_comment_creates_only_once(self):
    request = req("issue.comment", {"number": 3, "body": "A comment"})
    first = apply(request, self.backend)
    again = apply(request, self.backend)
    self.assertEqual(first[0], "applied")
    self.assertEqual(again[0], "unchanged")
    self.assertEqual(first[1]["comment_id"], "123")
    self.assertEqual(again[1]["comment_id"], "123")
    self.assertEqual(len(self.backend.comments), 1)

  def test_uncertain_comment_does_not_repeat_mutation(self):
    request = req("issue.comment", {"number": 3, "body": "A comment"})
    self.backend.reserve(request)
    with self.assertRaises(ProviderError) as exc:
      apply(request, self.backend)
    self.assertEqual(exc.exception.code, "unknown_outcome")
    self.assertEqual(self.backend.writes, [])

  def test_pr_creation_and_replay(self):
    p = {
      "source_ref": "refs/heads/work", "target_ref": "refs/heads/main",
      "expected_source_sha": SHA, "title": "New PR",
      "body": "Description", "draft": True,
    }
    request = req("pull_request.create", p)
    first = apply(request, self.backend)
    again = apply(request, self.backend)
    self.assertEqual(first[0], "applied")
    self.assertEqual(again[0], "unchanged")
    self.assertEqual(first[1]["head_sha"], SHA)
    self.assertEqual(len(self.backend.writes), 1)

  def test_pr_create_rejects_stale_source(self):
    self.backend.refs["refs/heads/work"] = OTHER
    p = {
      "source_ref": "refs/heads/work", "target_ref": "refs/heads/main",
      "expected_source_sha": SHA, "title": "New PR",
      "body": "", "draft": True,
    }
    with self.assertRaises(ProviderError) as exc:
      apply(req("pull_request.create", p), self.backend)
    self.assertEqual(exc.exception.code, "conflict")
    self.assertEqual(self.backend.writes, [])

  def test_pr_update_and_retry(self):
    request = req("pull_request.update", {
      "number": 7, "expected_head_sha": SHA, "title": "Changed",
    })
    self.assertEqual(apply(request, self.backend)[0], "applied")
    self.assertEqual(apply(request, self.backend)[0], "unchanged")
    self.assertEqual(self.backend.pr["title"], "Changed")
    self.assertEqual(len(self.backend.writes), 1)

  def test_pr_update_rejects_stale_head(self):
    self.backend.pr["head"]["sha"] = OTHER
    request = req("pull_request.update", {
      "number": 7, "expected_head_sha": SHA, "title": "Changed",
    })
    with self.assertRaises(ProviderError) as exc:
      apply(request, self.backend)
    self.assertEqual(exc.exception.code, "conflict")
    self.assertEqual(self.backend.writes, [])

  def test_merge_and_check_publication_refuse_without_authority(self):
    for operation in ("pull_request.merge", "check.publish"):
      with self.subTest(operation=operation):
        with self.assertRaises(ProviderError) as exc:
          apply(req(operation, {}), self.backend)
        self.assertEqual(exc.exception.code, "unsupported")
    self.assertEqual(self.backend.writes, [])


if __name__ == "__main__":
  unittest.main()
