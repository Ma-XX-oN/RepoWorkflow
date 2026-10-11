from dataclasses import replace

import pytest

from repo_workflow.remote_stable_publisher import (
  PublicationRefused,
  PublicationRequest,
  publish_stable_tag,
)


SHA = "a" * 40
BASE = "b" * 40


class Provider:
  def __init__(self):
    self.tip = SHA
    self.base = BASE
    self.tags = {}
    self.identity = True
    self.fail_after_create = False
    self.creates = 0

  def authenticated_finalizer(self):
    return self.identity

  def main_tip(self, repository):
    return self.tip

  def accepted_base(self, repository, sha):
    return self.base

  def read_tag(self, repository, ref):
    return self.tags.get(ref)

  def create_tag_if_absent(self, repository, ref, sha):
    self.creates += 1
    if ref in self.tags:
      raise RuntimeError("already exists")
    self.tags[ref] = sha
    if self.fail_after_create:
      raise TimeoutError("delayed response")


class Authority:
  def __init__(self):
    self.allowed = True
    self.accepted = True

  def authorize(self, request, ref):
    return self.allowed

  def certified(self, request, ref):
    return self.accepted


@pytest.fixture
def context():
  return (
    PublicationRequest("owner/repo", "1.2.3", SHA, SHA, BASE, "request-1"),
    Provider(),
    Authority(),
  )


def test_success_and_identical_replay(context):
  request, provider, authority = context
  assert publish_stable_tag(request, provider, authority) == "refs/tags/v1.2.3"
  assert publish_stable_tag(request, provider, authority) == "refs/tags/v1.2.3"
  assert provider.creates == 1


def test_delayed_response_reconciles(context):
  request, provider, authority = context
  provider.fail_after_create = True
  assert publish_stable_tag(request, provider, authority) == "refs/tags/v1.2.3"


@pytest.mark.parametrize("field,value", [
  ("version", "1.2.3-CI-FAIL"),
  ("version", "PRELIM-1.2.3"),
  ("version", "v1.2.3"),
  ("landed_sha", "bad"),
  ("candidate_sha", BASE),
  ("expected_base_sha", "bad"),
  ("repository", ""),
  ("request_id", ""),
])
def test_invalid_request_refused(context, field, value):
  request, provider, authority = context
  with pytest.raises(PublicationRefused):
    publish_stable_tag(replace(request, **{field: value}), provider, authority)
  assert provider.creates == 0


@pytest.mark.parametrize("failure", [
  "identity", "authority", "certification", "stale", "base", "conflict"
])
def test_refusals_never_mutate(context, failure):
  request, provider, authority = context
  if failure == "identity":
    provider.identity = False
  elif failure == "authority":
    authority.allowed = False
  elif failure == "certification":
    authority.accepted = False
  elif failure == "stale":
    provider.tip = BASE
  elif failure == "base":
    provider.base = SHA
  elif failure == "conflict":
    provider.tags["refs/tags/v1.2.3"] = BASE
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request, provider, authority)
  assert provider.creates == 0


def test_failed_create_does_not_claim_success(context):
  request, provider, authority = context

  def fail(repository, ref, sha):
    raise ConnectionError("unavailable")

  provider.create_tag_if_absent = fail
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request, provider, authority)


def test_competing_creator_identical_sha(context):
  request, provider, authority = context

  def race(repository, ref, sha):
    provider.tags[ref] = sha
    raise RuntimeError("already created")

  provider.create_tag_if_absent = race
  assert publish_stable_tag(request, provider, authority) == "refs/tags/v1.2.3"


def test_competing_creator_conflicting_sha(context):
  request, provider, authority = context

  def race(repository, ref, sha):
    provider.tags[ref] = BASE
    raise RuntimeError("already created")

  provider.create_tag_if_absent = race
  with pytest.raises(PublicationRefused):
    publish_stable_tag(request, provider, authority)
