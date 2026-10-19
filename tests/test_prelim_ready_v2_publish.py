"""A published #102 PASS identity alone authorizes first READY creation."""
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_v2_publish import publish_destination_prelim


G = "11111111-1111-4111-8111-111111111111"
C = "c"*40
S = "a"*40
B = "b"*40


class NotFound(Exception):
  code = "not_found"


class Backend:
  repository = "Org/Repo"
  def __init__(self):
    self.refs = {}
    self.writes = []
    self.candidate_available = True

  def get(self, route):
    if route.startswith("git/commits/"):
      if not self.candidate_available:
        raise NotFound()
      return {"sha": route.removeprefix("git/commits/")}
    ref = "refs/" + route.removeprefix("git/ref/")
    if ref not in self.refs:
      raise NotFound()
    return {"ref": ref, "object": {"sha": self.refs[ref]}}

  def post(self, route, record):
    assert route == "git/refs"
    ref = record["ref"]
    if ref in self.refs:
      raise AssertionError("duplicate provider ref")
    self.refs[ref] = record["sha"]
    self.writes.append(record)
    return {"ref": ref}


class QualifiedPublishTests(unittest.TestCase):
  def setUp(self):
    self.backend = Backend()
    self.identity = {
      "kind": "destination-qualified-v2", "attempt": G,
      "issue": "7", "destination": "issue-10",
      "source_sha": S, "base_sha": B, "candidate_sha": C,
      "proposed_version": "1.2.4", "test_version": "1.2.4",
      "regression_tag": "v1.2.4-REGRESSION-PASS",
      "integration_tag": "v1.2.4-INTEGRATION-PASS",
      "outcome": "PASS",
    }
    self.root = Path(".")
    self.remote = {"refs/heads/main": B,
      "refs/heads/issue-10": B,
      "refs/heads/prelim-v2-identity-state/" + G: "f"*40}
    self.parent = "issue-10"
    self.tag_sha = C

  def publish(self, request_id="publish-7", read_record=None):
    with (
      patch("repo_workflow.prelim_ready_v2_publish.verify_ready_provider_scope"),
      patch("repo_workflow.prelim_ready_v2_publish._remote_ref",
            side_effect=lambda root, remote, ref: self.remote.get(ref)),
      patch("repo_workflow.prelim_ready_v2_publish._restore"),
      patch("repo_workflow.prelim_ready_v2_publish.durable_store",
            return_value=self),
      patch("repo_workflow.prelim_ready_v2_publish._remote_target",
            side_effect=lambda root, remote, tag: self.tag_sha),
    ):
      return publish_destination_prelim(
        self.root, {"repository": {"authoritativeRemote": "origin"}},
        ticket=7, destination="issue-10", guid=G, request_id=request_id,
        backend=self.backend, resolve_parent=lambda issue: self.parent,
        read_publication_record=read_record,
      )

  def read(self, key):
    assert key == "prelim/v2-identities/" + G
    return {"value": dict(self.identity)}

  def test_accepted_nonmain_candidate_publishes_one_ready_ref(self):
    result = self.publish()
    self.assertEqual(result.sha, C)
    self.assertEqual(result.ref, "refs/heads/PRELIM-issue-7/issue-10-" + G)
    self.assertEqual(len(self.backend.writes), 1)
    self.assertEqual(set(self.backend.refs), {result.ref})

  def test_idempotency_requires_authenticated_request_record(self):
    first = self.publish()
    with self.assertRaisesRegex(ReadyPublicationError, "already exists"):
      self.publish()
    result = self.publish(read_record=lambda request_id: {
      "ref": first.ref, "sha": C, "status": "published",
      "request_id": request_id,
    })
    self.assertEqual(result, first)
    self.assertEqual(len(self.backend.writes), 1)

  def test_destination_advances_after_offline_pass(self):
    self.remote["refs/heads/issue-10"] = "e"*40
    self.assertEqual(self.publish().sha, C)

  def test_wrong_parent_or_missing_parent_denied(self):
    self.parent = "main"
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.parent = "issue-10"
    self.remote.pop("refs/heads/issue-10")
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.assertFalse(self.backend.writes)

  def test_changed_tags_or_forged_pass_denied(self):
    self.tag_sha = "d"*40
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.tag_sha = C
    self.identity["outcome"] = "FAIL"
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.assertFalse(self.backend.writes)

  def test_missing_provider_candidate_object_refuses_ready(self):
    self.backend.candidate_available = False
    with self.assertRaisesRegex(ReadyPublicationError, "object unavailable"):
      self.publish()
    self.assertFalse(self.backend.writes)

  def test_old_main_candidate_cannot_impersonate_v2(self):
    self.identity.pop("kind")
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.assertFalse(self.backend.writes)


if __name__ == "__main__":
  unittest.main()
