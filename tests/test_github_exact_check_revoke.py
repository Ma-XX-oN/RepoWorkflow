"""Negative tests for post-publication failure recovery."""
import unittest

from repo_workflow.github_exact_check import (
  CONTEXT, PublishError, VerifiedDecision, publish,
)

SHA = "a" * 40
BASE = "b" * 40


class Provider:
  def __init__(self, *, changed_after=False, bad_readback=False):
    self.posts = []
    self.base_reads = 0
    self.changed_after = changed_after
    self.bad_readback = bad_readback

  def __call__(self, path, payload=None):
    if path == "/branches/main":
      self.base_reads += 1
      sha = ("c" * 40 if self.changed_after and self.base_reads > 2
             else BASE)
      return {"commit": {"sha": sha}}
    if path == "/commits/" + SHA + "/statuses":
      if not self.posts:
        return []
      value = self.posts[-1]
      state = value["state"]
      if self.bad_readback and len(self.posts) == 1:
        state = "failure"
      return [{"id": 20 + len(self.posts), "context": CONTEXT,
               "state": state, "creator": {"login": "runner"}}]
    if path == "/statuses/" + SHA:
      self.posts.append(payload)
      return {"id": 20 + len(self.posts), "context": CONTEXT,
              "state": payload["state"], "creator": {"login": "runner"}}
    raise AssertionError(path)


def verify(_, sha, base):
  return VerifiedDecision(sha, base, "provider-proof", "runner", True)


class RevocationTests(unittest.TestCase):
  def test_changed_base_after_write_revoked(self):
    p = Provider(changed_after=True)
    with self.assertRaises(PublishError):
      publish("user/disposable", SHA, BASE, "main", "token",
              evidence={}, verifier=verify, provider=p)
    self.assertEqual([x["state"] for x in p.posts],
                     ["success", "failure"])

  def test_readback_failure_revoked(self):
    p = Provider(bad_readback=True)
    with self.assertRaises(PublishError):
      publish("user/disposable", SHA, BASE, "main", "token",
              evidence={}, verifier=verify, provider=p)
    self.assertEqual([x["state"] for x in p.posts],
                     ["success", "failure"])


if __name__ == "__main__":
  unittest.main()
