"""Durable record-to-READY bridge must reject stale and wrong owners."""
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_recorded import (
  publish_recorded_ready, publish_recorded_ready_certified,
)

G="11111111-1111-4111-8111-111111111111"
C="c"*40
S="a"*40
B="b"*40


class Backend:
  def __init__(self):
    self.refs={}
    self.posts=[]

  def get(self, path):
    ref="refs/"+path.removeprefix("git/ref/")
    if ref not in self.refs:
      class Missing(Exception):
        code="not_found"
      raise Missing()
    return {"ref":ref,"object":{"sha":self.refs[ref]}}

  def post(self, path, values):
    self.posts.append((path,values))
    if values["ref"] in self.refs:
      raise AssertionError("duplicate ref")
    self.refs[values["ref"]]=values["sha"]


class RecordedReadyTests(unittest.TestCase):
  def setUp(self):
    self.backend=Backend()
    self.value={
      "attempt":G,"issue":"123","branch":"prelim-main-"+G,
      "source_ref":"refs/heads/issue-123-fix",
      "source_sha":S,"base_sha":B,"candidate_sha":C,
      "state":"ready","lifecycle_revision":5,
      "proposed_version":"1.2.3",
    }
    self.record={"value":self.value,"revision":7}
    self.authority=True

  def publish(self):
    with (
      patch("repo_workflow.prelim_ready_recorded.durable_store",
            return_value=object()),
      patch("repo_workflow.prelim_ready_recorded._record",
            return_value=self.record),
      patch("repo_workflow.prelim_ready_recorded._remote_ref",
            return_value=C),
      patch("repo_workflow.prelim_ready_recorded._trusted_inputs"),
    ):
      return publish_recorded_ready(
        Path("."), {"repository":{"authoritativeRemote":"origin"}},
        ticket=123,destination="main",guid=G,request_id="publish-123",
        backend=self.backend,
        verify_parent_and_evidence=lambda info:self.authority)

  def test_authoritative_stored_commit_is_published_once(self):
    result=self.publish()
    self.assertEqual(result.sha,C)
    self.assertEqual(len(self.backend.posts),1)
    self.assertEqual(result.ref,"refs/heads/PRELIM-issue-123/main-"+G)

  def test_owner_mismatch_fails_before_any_ref_write(self):
    self.value["issue"]="456"
    with self.assertRaisesRegex(ReadyPublicationError,"owner"):
      self.publish()
    self.assertFalse(self.backend.posts)

  def test_prepared_not_ready_fails_closed(self):
    self.value["state"]="prepared"
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.assertFalse(self.backend.posts)

  def test_unverified_parent_or_candidate_denies(self):
    self.authority=False
    with self.assertRaises(ReadyPublicationError):
      self.publish()
    self.assertFalse(self.backend.posts)

  def test_certified_entrypoint_requires_real_published_pass(self):
    from unittest.mock import patch
    with (
      patch("repo_workflow.prelim_ready_recorded.durable_store",
            return_value=object()),
      patch("repo_workflow.prelim_ready_recorded._record",
            return_value=self.record),
      patch("repo_workflow.prelim_ready_recorded._remote_ref",
            return_value=C),
      patch("repo_workflow.prelim_ready_recorded._trusted_inputs"),
      patch("repo_workflow.prelim_ready_authority.verify_ready_authority",
            return_value=False) as verify,
    ):
      with self.assertRaises(ReadyPublicationError):
        publish_recorded_ready_certified(
          Path("."),{"repository":{"authoritativeRemote":"origin"}},
          ticket=123,destination="main",guid=G,
          request_id="published-123",backend=self.backend,
          resolve_parent=lambda ticket:"main")
    self.assertTrue(verify.called)
    self.assertEqual(self.backend.posts, [])

  def test_second_call_cannot_adopt_prior_published_ref(self):
    self.publish()
    with self.assertRaisesRegex(ReadyPublicationError,"already exists"):
      self.publish()
    self.assertEqual(len(self.backend.posts),1)


if __name__=="__main__":
  unittest.main()
