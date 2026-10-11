import unittest

from repo_workflow.github_stable_tag_provider import (
  GitHubStableTagProvider, Response,
)
from repo_workflow.remote_stable_publisher import (
  PublicationRefused, PublicationRequest, publish_stable_tag,
)


SHA = "a" * 40
BASE = "b" * 40


class FakeGitHub:
  def __init__(self):
    self.tags = {}
    self.calls = []
    self.fail = False
    self.race = None

  def __call__(self, method, path, body):
    self.calls.append((method, path, body))
    if self.fail:
      raise TimeoutError()
    if path == "/user":
      return Response(200, {"login": "release-bot"})
    if path.endswith("/git/ref/heads/main"):
      return Response(200, {"object": {"type": "commit", "sha": SHA}})
    if path.endswith("/git/commits/" + SHA):
      return Response(200, {"parents": [{"sha": BASE}]})
    if "/git/tags/" in path:
      return Response(200, {"object": {"type": "commit", "sha": SHA}})
    if method == "GET" and "/git/ref/tags/" in path:
      tag = path.rsplit("/", 1)[-1]
      if tag not in self.tags:
        return Response(404, {})
      return Response(200, {"object": self.tags[tag]})
    if method == "POST" and path.endswith("/git/refs"):
      tag = body["ref"].split("/")[-1]
      if self.race is not None:
        self.tags[tag] = self.race
        return Response(422, {"message": "already exists"})
      if tag in self.tags:
        return Response(422, {})
      self.tags[tag] = {"type": "commit", "sha": body["sha"]}
      return Response(201, {"ref": body["ref"]})
    return Response(404, {})


class Authority:
  def authorize(self, request, ref):
    return True

  def certified(self, request, ref):
    return True


def request():
  return PublicationRequest("owner/repo", "1.2.3", SHA, SHA, BASE, "one", "auth-1", "protection-1", "cert-1", "patch")


class GitHubProviderTests(unittest.TestCase):
  def setUp(self):
    self.api = FakeGitHub()
    self.provider = GitHubStableTagProvider(
      self.api, "release-bot", "release-bot"
    )

  def publish(self):
    return publish_stable_tag(request(), self.provider, Authority())

  def test_publish_and_replay(self):
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")
    self.assertEqual(self.publish(), "refs/tags/v1.2.3")
    self.assertEqual(sum(
      method == "POST" for method, _, _ in self.api.calls
    ), 1)

  def test_annotated_tag_peeling(self):
    self.api.tags["v1.2.3"] = {"type": "tag", "sha": "c" * 40}
    self.assertEqual(
      self.provider.read_tag("owner/repo", "refs/tags/v1.2.3"), SHA
    )

  def test_authenticated_identity_required(self):
    self.provider = GitHubStableTagProvider(
      self.api, "attacker", "release-bot"
    )
    with self.assertRaises(PublicationRefused):
      self.publish()
    self.assertFalse(any(
      method == "POST" for method, _, _ in self.api.calls
    ))

  def test_invalid_remote_refs(self):
    for value in (
      {"type": "commit", "sha": BASE},
      {"type": "blob", "sha": SHA},
    ):
      with self.subTest(value=value):
        self.api.tags["v1.2.3"] = value
        with self.assertRaises(PublicationRefused):
          self.publish()

  def test_concurrent_atomic_create(self):
    for sha in (SHA, BASE):
      with self.subTest(sha=sha):
        self.setUp()
        self.api.race = {"type": "commit", "sha": sha}
        if sha == SHA:
          self.assertEqual(self.publish(), "refs/tags/v1.2.3")
        else:
          with self.assertRaises(PublicationRefused):
            self.publish()

  def test_transport_unavailable_fails_closed(self):
    self.api.fail = True
    with self.assertRaises(PublicationRefused):
      self.publish()


if __name__ == "__main__":
  unittest.main()
