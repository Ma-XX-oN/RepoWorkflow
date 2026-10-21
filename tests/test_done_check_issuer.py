"""Independent GitHub App release/MIT check-run verification tests."""
from dataclasses import replace
import unittest

from repo_workflow.done_check_issuer import (
  CheckIssuerBinding,CheckIssuerError,_external_id,verify_check_stage,
)
from repo_workflow.done_stage_certification import (
  MitTimedOut,StageFailed,
)

A="a"*40
B="b"*40


class CheckIssuerTests(unittest.TestCase):
  def setUp(self):
    self.binding=CheckIssuerBinding(
      "Org/Repo","release",109,A,B,12345,89123,
      "check-12345-authority","catalogue","config","inputs",
      "2027-12-31T00:00:00Z")
    self.reads=[]
    self.changed=False

  def check(self,binding=None,**changes):
    b=binding or self.binding
    value={
      "id":b.check_run_id,
      "name":{"release":"rwf-done-release",
              "MIT":"rwf-done-manual-test"}[b.stage],
      "head_sha":b.source_sha,
      "external_id":_external_id(b),
      "app":{"id":b.app_id,"slug":"independent-release-tester"},
      "status":"completed","conclusion":"success",
    }
    return {**value,**changes}

  def read(self,repo,check_run_id):
    self.reads.append((repo,check_run_id))
    if self.changed and len(self.reads)==2:
      return self.check(conclusion="failure")
    return self.check()

  def invoke(self,**changes):
    p={"binding":self.binding,
       "trusted_app_id":89123,"read_check":self.read}
    return verify_check_stage(**{**p,**changes})

  def test_successful_release_has_independent_app_and_source_identity(self):
    stage=self.invoke()
    self.assertEqual(stage.stage,"release")
    self.assertEqual(stage.status,"PASS")
    self.assertEqual(stage.source_sha,A)
    self.assertEqual(stage.parent_sha,B)
    self.assertTrue(stage.independently_authenticated)
    self.assertEqual(self.reads,[("Org/Repo",12345)]*2)

  def test_genuine_manual_pass_is_distinct_from_release(self):
    self.binding=replace(self.binding,stage="MIT",tester_id="human-109")
    stage=self.invoke()
    self.assertEqual(stage.stage,"MIT")
    self.assertEqual(stage.status,"PASS")

  def test_release_or_manual_fail_is_not_inferred_pass(self):
    for name in ("release","MIT"):
      self.binding=replace(
        self.binding,stage=name,
        tester_id="human-109" if name=="MIT" else None)
      with self.subTest(name=name):
        with self.assertRaises(StageFailed) as failed:
          self.invoke(read_check=lambda *x:self.check(
            conclusion="failure"))
        self.assertEqual(failed.exception.stage,name)

  def test_manual_timeout_is_not_a_failure_or_success(self):
    self.binding=replace(
      self.binding,stage="MIT",tester_id="human-109")
    with self.assertRaises(MitTimedOut):
      self.invoke(read_check=lambda *x:self.check(
        conclusion="timed_out"))

  def test_release_timeout_is_unverified(self):
    with self.assertRaisesRegex(CheckIssuerError,"no PASS"):
      self.invoke(read_check=lambda *x:self.check(
        conclusion="timed_out"))

  def test_github_actions_cannot_claim_independent_release(self):
    with self.assertRaisesRegex(CheckIssuerError,"foreign"):
      self.invoke(read_check=lambda *x:self.check(
        app={"id":89123,"slug":"github-actions"}))

  def test_changed_app_or_untrusted_app_cannot_approve(self):
    with self.assertRaisesRegex(CheckIssuerError,"foreign"):
      self.invoke(read_check=lambda *x:self.check(
        app={"id":7777,"slug":"foreign-app"}))
    with self.assertRaisesRegex(CheckIssuerError,"binding required"):
      self.invoke(trusted_app_id=7777)

  def test_wrong_source_parent_or_material_inputs_rejected(self):
    for change in ({"head_sha":B},{"external_id":"wrong-parent"},
                   {"id":54321}):
      with self.subTest(change=change):
        with self.assertRaisesRegex(CheckIssuerError,"foreign"):
          self.invoke(read_check=lambda *x:self.check(**change))

  def test_status_transition_during_double_read_denied(self):
    self.changed=True
    with self.assertRaisesRegex(CheckIssuerError,"changed"):
      self.invoke()
    self.assertEqual(len(self.reads),2)

  def test_provider_unavailable_cannot_be_substituted(self):
    def broken(*args):
      raise TimeoutError("GitHub check unavailable")
    with self.assertRaisesRegex(CheckIssuerError,"UNKNOWN"):
      self.invoke(read_check=broken)

  def test_mit_requires_explicit_tester_identity(self):
    self.binding=replace(self.binding,stage="MIT")
    with self.assertRaisesRegex(CheckIssuerError,"binding required"):
      self.invoke()
    self.assertEqual(self.reads,[])

  def test_in_progress_check_refused(self):
    with self.assertRaisesRegex(CheckIssuerError,"incomplete"):
      self.invoke(read_check=lambda *x:self.check(
        status="in_progress",conclusion=None))

  def test_unsupported_issuer_status_cannot_be_used(self):
    with self.assertRaisesRegex(CheckIssuerError,"foreign"):
      self.invoke(read_check=lambda *x:self.check(
        conclusion="neutral"))


if __name__=="__main__":
  unittest.main()
