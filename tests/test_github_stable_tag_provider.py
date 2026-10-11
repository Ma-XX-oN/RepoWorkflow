import pytest

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
  return PublicationRequest("owner/repo", "1.2.3", SHA, SHA, BASE, "one")


def test_real_github_rest_contract_replay():
  api = FakeGitHub()
  provider = GitHubStableTagProvider(api, "release-bot", "release-bot")
  assert publish_stable_tag(request(), provider, Authority()) == (
    "refs/tags/v1.2.3"
  )
  assert publish_stable_tag(request(), provider, Authority()) == (
    "refs/tags/v1.2.3"
  )
  assert sum(method == "POST" for method, _, _ in api.calls) == 1


def test_annotated_tag_peeling():
  api = FakeGitHub()
  api.tags["v1.2.3"] = {"type": "tag", "sha": "c" * 40}
  provider = GitHubStableTagProvider(api, "release-bot", "release-bot")
  assert provider.read_tag("owner/repo", "refs/tags/v1.2.3") == SHA


def test_authenticated_identity_required():
  api = FakeGitHub()
  provider = GitHubStableTagProvider(api, "attacker", "release-bot")
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request(), provider, Authority())
  assert not any(method == "POST" for method, _, _ in api.calls)


@pytest.mark.parametrize("value", [
  {"type": "commit", "sha": BASE},
  {"type": "blob", "sha": SHA},
])
def test_nonmatching_and_invalid_remote_refs(value):
  api = FakeGitHub()
  api.tags["v1.2.3"] = value
  provider = GitHubStableTagProvider(api, "release-bot", "release-bot")
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request(), provider, Authority())


@pytest.mark.parametrize("race", [
  {"type": "commit", "sha": SHA},
  {"type": "commit", "sha": BASE},
])
def test_concurrent_atomic_create(race):
  api = FakeGitHub()
  api.race = race
  provider = GitHubStableTagProvider(api, "release-bot", "release-bot")
  if race["sha"] == SHA:
    assert publish_stable_tag(request(), provider, Authority()) == (
      "refs/tags/v1.2.3"
    )
  else:
    with pytest.raises(PublicationRefused):
      publish_stable_tag(request(), provider, Authority())


def test_transport_unavailable_fails_closed():
  api = FakeGitHub()
  api.fail = True
  provider = GitHubStableTagProvider(api, "release-bot", "release-bot")
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request(), provider, Authority())
