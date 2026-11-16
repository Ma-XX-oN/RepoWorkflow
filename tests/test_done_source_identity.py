"""Invocation-only SHA peeling preserves source identity or rejects."""
from dataclasses import replace
import unittest

from repo_workflow.done_source_identity import (
  EffectiveSource, InvocationCommit, SourceIdentityError,
  peel_tested_source,
)

A,B,C,D=("a"*40,"b"*40,"c"*40,"d"*40)


class IdentityTests(unittest.TestCase):
  def setUp(self):
    self.nodes={
      B:InvocationCommit(B,(A,),(".ci/rwf",),".ci/rwf"),
      C:InvocationCommit(C,(B,),(".ci/run",),".ci/run"),
      D:InvocationCommit(D,(C,),(".ci/rwf",),".ci/rwf"),
    }
    self.reads=[]
    self.auth=[]
  def read(self,sha):
    self.reads.append(sha)
    return self.nodes[sha]
  def verify(self,node,tested):
    self.auth.append(node.sha)
    return tested==A
  def peel(self,head=D,source=A,**options):
    return peel_tested_source(
      command_head_sha=head,expected_tested_sha=source,
      read_commit=self.read,verify_invocation=self.verify,**options)

  def test_zero_trailing_request_is_identity(self):
    result=self.peel(head=A)
    self.assertEqual(result,EffectiveSource(A,A,()))
    self.assertEqual(self.reads,[])

  def test_one_and_three_exact_authenticated_requests(self):
    self.assertEqual(len(self.peel(head=B).peeled_requests),1)
    self.reads=[]
    output=self.peel()
    self.assertEqual(output.tested_source_sha,A)
    self.assertEqual(len(output.peeled_requests),3)
    self.assertEqual(self.reads,[D,C,B])
    self.assertEqual(self.auth[-3:],[D,C,B])

  def test_mixed_content_invocation_is_never_peeled(self):
    self.nodes[D]=replace(self.nodes[D],
      changed_paths=(".ci/rwf","app.py"))
    with self.assertRaisesRegex(SourceIdentityError,"mixed"):
      self.peel()

  def test_merge_commit_invocation_is_never_peeled(self):
    self.nodes[D]=replace(self.nodes[D],parents=(C,A))
    with self.assertRaisesRegex(SourceIdentityError,"mixed"):
      self.peel()

  def test_forged_request_cannot_peel_source_history(self):
    with self.assertRaisesRegex(SourceIdentityError,"not authenticated"):
      peel_tested_source(
        command_head_sha=D,expected_tested_sha=A,
        read_commit=self.read,verify_invocation=lambda *_:False)

  def test_material_change_before_tested_source_is_rejected(self):
    self.nodes[C]=replace(
      self.nodes[C],changed_paths=("source.py",),
      invocation_marker=None)
    with self.assertRaisesRegex(SourceIdentityError,"material"):
      self.peel()

  def test_wrong_tested_sha_is_never_rewritten(self):
    with self.assertRaises(SourceIdentityError):
      self.peel(source="e"*40)

  def test_missing_or_malformed_request_proof_fails_closed(self):
    with self.assertRaisesRegex(SourceIdentityError,"readers"):
      peel_tested_source(command_head_sha=D,expected_tested_sha=A,
                         read_commit=self.read,verify_invocation=None)
    self.nodes[D]=replace(self.nodes[D],parents=())
    with self.assertRaises(SourceIdentityError):
      self.peel()

  def test_over_limit_refuses_too_many_requests(self):
    with self.assertRaisesRegex(SourceIdentityError,"mixed"):
      self.peel(max_requests=2)


if __name__=="__main__":
  unittest.main()
