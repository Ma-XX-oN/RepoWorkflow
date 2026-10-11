import unittest

from repo_workflow.github_exact_check import (
  CONTEXT, PublishError, VerifiedDecision, publish,
)

SHA = "a" * 40
BASE = "b" * 40


class Provider:
  def __init__(self, *, changed=False, denied=False, forged=False):
    self.posts = []
    self.changed = changed
    self.denied = denied
    self.forged = forged
    self.reads = 0

  def __call__(self, path, payload=None):
    if path.startswith("/branches/"):
      self.reads += 1
      return {"commit": {"sha": "c" * 40 if self.changed and
                         self.reads > 1 else BASE}}
    if path == "/statuses/" + SHA:
      self.posts.append(payload)
      if self.denied:
        raise OSError("denied")
      return {"id": 21, "sha": BASE if self.forged else SHA,
              "context": CONTEXT, "state": "success",
              "creator": {"login": "runner"}}
    if path == "/commits/" + SHA + "/statuses":
      return [{"id": 21, "context": CONTEXT, "state": "success",
               "creator": {"login": "runner"}}]
    raise AssertionError(path)


def approved(_, sha, base):
  return VerifiedDecision(sha, base, "authenticated-run-123", "runner", True)


class ExactCheckTests(unittest.TestCase):
  def call(self, provider, verifier=approved, base=BASE):
    return publish("user/disposable", SHA, base, "main", "token",
                   evidence={"untrusted": True}, verifier=verifier,
                   provider=provider)

  def test_positive_readback(self):
    provider = Provider()
    self.assertEqual(self.call(provider)["status_id"], 21)
    self.assertEqual(provider.posts[0]["context"], CONTEXT)

  def test_missing_evidence(self):
    p = Provider()
    with self.assertRaises(PublishError):
      self.call(p, lambda *_: None)
    self.assertEqual(p.posts, [])

  def test_forged_verdict(self):
    p = Provider()
    with self.assertRaises(PublishError):
      self.call(p, lambda *_: {"allowed": True})
    self.assertEqual(p.posts, [])

  def test_incomplete(self):
    p = Provider()
    with self.assertRaises(PublishError):
      self.call(p, lambda _, sha, base:
                VerifiedDecision(sha, base, "id", "runner", False))
    self.assertEqual(p.posts, [])

  def test_stale_base(self):
    p = Provider()
    with self.assertRaises(PublishError):
      self.call(p, base="c" * 40)
    self.assertEqual(p.posts, [])

  def test_moving_base(self):
    p = Provider(changed=True)
    with self.assertRaises(PublishError):
      self.call(p)
    self.assertEqual(p.posts, [])

  def test_denied_provider(self):
    with self.assertRaises(PublishError):
      self.call(Provider(denied=True))

  def test_forged_provider(self):
    with self.assertRaises(PublishError):
      self.call(Provider(forged=True))

  def test_invalid_sha(self):
    p = Provider()
    with self.assertRaises(PublishError):
      publish("user/disposable", "x" * 40, BASE, "main", "token",
              evidence={}, verifier=approved, provider=p)
    self.assertEqual(p.posts, [])


if __name__ == "__main__":
  unittest.main()
