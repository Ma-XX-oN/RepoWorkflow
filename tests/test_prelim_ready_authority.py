"""Published #102 PASS proof binds READY source, parent and test tags."""
from unittest.mock import patch
import unittest

from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_bridge import PreparedIdentity
from repo_workflow.prelim_ready_authority import verify_ready_authority

G = "11111111-1111-4111-8111-111111111111"
S, B, C = "a"*40, "b"*40, "c"*40


class Store:
  def __init__(self, value):
    self.value = value
  def read(self, key):
    return {"value":self.value}


class ReadyAuthorityTests(unittest.TestCase):
  def setUp(self):
    self.identity = PreparedIdentity(123, "main", S, B, C, G)
    self.value = {
      "attempt":G,"issue":"123",
      "candidate_sha":C,"source_sha":S,"base_sha":B,
      "outcome":"PASS",
      "regression_tag":"v1.2.3-REGRESSION-PASS",
      "integration_tag":"v1.2.3-INTEGRATION-PASS",
    }
    self.refs = {
      "refs/heads/main":B,
      "refs/heads/prelim-identity-state/"+G:"d"*40,
    }
    self.parent = "main"
    self.targets = {x:C for x in
      (self.value["regression_tag"],self.value["integration_tag"])}

  def verify(self):
    with (
      patch("repo_workflow.prelim_ready_authority._remote_ref",
        side_effect=lambda root,remote,ref:self.refs.get(ref)),
      patch("repo_workflow.prelim_ready_authority.restore_identity"),
      patch("repo_workflow.prelim_ready_authority.durable_store",
        return_value=Store(self.value)),
      patch("repo_workflow.prelim_ready_authority._remote_target",
        side_effect=lambda root,remote,tag:self.targets.get(tag)),
    ):
      return verify_ready_authority(
        ".", "origin", self.identity,
        resolve_parent=lambda ticket:self.parent)

  def test_complete_published_pass(self):
    self.assertTrue(self.verify())

  def test_immediate_child_mismatch_denied(self):
    self.parent = "issue-10"
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_legacy_main_candidate_not_validated_for_other_parent(self):
    self.identity = PreparedIdentity(123, "issue-10", S, B, C, G)
    self.parent = "issue-10"
    self.refs["refs/heads/issue-10"] = B
    with self.assertRaisesRegex(ReadyPublicationError, "provenance"):
      self.verify()

  def test_destination_advanced_allows_immutable_ready_publication(self):
    self.refs["refs/heads/main"]="e"*40
    self.assertTrue(self.verify())

  def test_destination_disappeared_denied(self):
    self.refs.pop("refs/heads/main")
    with self.assertRaisesRegex(ReadyPublicationError,"missing"):
      self.verify()

  def test_missing_published_identity_denied(self):
    self.refs.pop("refs/heads/prelim-identity-state/"+G)
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_stale_candidate_proof_denied(self):
    self.value["candidate_sha"]="e"*40
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_non_pass_cannot_publish(self):
    self.value["outcome"]="FAIL"
    with self.assertRaises(ReadyPublicationError):
      self.verify()

  def test_changed_regression_or_integration_tags_denied(self):
    for tag in list(self.targets):
      original=self.targets[tag]
      self.targets[tag]="e"*40
      with self.subTest(tag=tag):
        with self.assertRaises(ReadyPublicationError):
          self.verify()
      self.targets[tag]=original

  def test_missing_tags_denied(self):
    self.value.pop("integration_tag")
    with self.assertRaises(ReadyPublicationError):
      self.verify()


if __name__=="__main__":
  unittest.main()
