"""Immutable provider operation intent: collision, lost ACK, restart tests."""
import unittest

from adapters.repo_host_github_integration_intent import (
  AcceptanceIntentError, publish_intent, read_intent,
)

REPO="Org/Repo"
BASE="a"*40
TREE="b"*40
PROPOSED="c"*40
GUID="11111111-1111-4111-8111-111111111111"


class Missing(Exception):
  code="not_found"


class FakeBackend:
  repository=REPO

  def __init__(self):
    self.tags={}
    self.commits={BASE:{"tree":{"sha":TREE},"message":"base"}}
    self.counter=0
    self.fail_after_create=False
    self.actor="trusted-finalizer"

  def identity(self):
    return {"login":self.actor}

  def get(self,path):
    if path.startswith("git/ref/tags/"):
      ref="refs/tags/"+path.removeprefix("git/ref/tags/")
      if ref not in self.tags:
        raise Missing()
      return {"ref":ref,"object":{"sha":self.tags[ref]}}
    if path.startswith("git/commits/"):
      return self.commits[path.removeprefix("git/commits/")]
    raise AssertionError(path)

  def post(self,path,data):
    if path=="git/commits":
      self.counter+=1
      sha=f"{self.counter:040x}"
      self.commits[sha]={**data,
        "parents":[{"sha":parent} for parent in data["parents"]]}
      return {"sha":sha}
    if path=="git/refs":
      if data["ref"] in self.tags:
        raise RuntimeError("competing create")
      self.tags[data["ref"]]=data["sha"]
      if self.fail_after_create:
        raise RuntimeError("GitHub accepted write but ACK lost")
      return data
    raise AssertionError(path)


def request(**changes):
  r={
    "repository":REPO, "destination":"integration",
    "guid":GUID,"accepted_sha":BASE,"expected_destination_sha":BASE,
    "proposed_sha":PROPOSED,
  }
  r.update(changes)
  return {"schema_version":2,"repository":REPO,
          "operation":"destination.accept","request_id":"accept-test-1",
          "parameters":{"record":r}}


class IntentTests(unittest.TestCase):
  def setUp(self):
    self.backend=FakeBackend()

  def test_missing_not_a_land_or_successful_authorization(self):
    self.assertIsNone(read_intent(self.backend,request()))
    self.assertEqual(self.backend.tags,{})

  def test_immutable_operation_round_trip_after_new_instance(self):
    first=publish_intent(self.backend,request())
    self.assertEqual(first["request_digest"],read_intent(
      self.backend,request())["request_digest"])
    other=FakeBackend()
    other.tags=dict(self.backend.tags)
    other.commits=dict(self.backend.commits)
    self.assertEqual(read_intent(other,request()),first)
    self.assertEqual(publish_intent(other,request()),first)
    self.assertEqual(len(other.tags),1)

  def test_lost_response_reconciles_only_exact_persisted_request(self):
    self.backend.fail_after_create=True
    item=publish_intent(self.backend,request())
    self.assertEqual(read_intent(self.backend,request()),item)
    self.assertEqual(len(self.backend.tags),1)

  def test_changed_candidate_source_or_destination_refuses_replay(self):
    publish_intent(self.backend,request())
    for changes in (
      {"proposed_sha":"f"*40},{"accepted_sha":"e"*40},
      {"destination":"elsewhere"},{"expected_destination_sha":"d"*40},
      {"guid":"22222222-2222-4222-8222-222222222222"},
    ):
      with self.subTest(changes=changes):
        with self.assertRaisesRegex(AcceptanceIntentError,"identity"):
          read_intent(self.backend,request(**changes))
        with self.assertRaises(AcceptanceIntentError):
          publish_intent(self.backend,request(**changes))
    self.assertEqual(len(self.backend.tags),1)

  def test_different_authenticated_actor_cannot_reuse_intent(self):
    publish_intent(self.backend,request())
    self.backend.actor="foreign-finalizer"
    with self.assertRaises(AcceptanceIntentError):
      read_intent(self.backend,request())

  def test_forged_or_malformed_tag_fails_closed(self):
    publish_intent(self.backend,request())
    ref=next(iter(self.backend.tags))
    sha=self.backend.tags[ref]
    self.backend.commits[sha]["parents"]=[{"sha":"f"*40}]
    with self.assertRaisesRegex(AcceptanceIntentError,"identity"):
      read_intent(self.backend,request())

  def test_transport_unknown_is_not_absence(self):
    def broken(path):
      raise RuntimeError("provider unavailable")
    self.backend.get=broken
    with self.assertRaisesRegex(AcceptanceIntentError,"UNKNOWN"):
      read_intent(self.backend,request())


if __name__=="__main__":
  unittest.main()
