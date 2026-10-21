"""Provider-style Git readback of canonical #583 records (isolated fixture)."""
import base64
from dataclasses import replace
from pathlib import Path
import subprocess
import unittest

from repo_workflow.done_shared_lifecycle import (
  SharedLifecycleError,SharedLifecycleEvidence,verify_shared_completion,
)
from tests.test_done_canonical_lifecycle import CanonicalLifecycleTests


class GitReadOnlyProvider:
  """Fixture implements immutable Git objects, not network authentication."""
  repository="Org/Repo"

  def __init__(self,root):
    self.root=root
    self.ref_reads=0
    self.move_on_second_ref=False
    self.forge_blob=False

  def git(self,*args):
    return subprocess.run(
      ["git","-C",str(self.root),*args],capture_output=True,
      check=True).stdout

  def get(self,path):
    if path.startswith("git/ref/heads/"):
      self.ref_reads+=1
      name=path[len("git/ref/heads/"):]
      sha=self.git("rev-parse","refs/heads/"+name).decode().strip()
      if self.move_on_second_ref and self.ref_reads==2:
        sha="f"*40
      return {"ref":"refs/heads/"+name,"object":{"sha":sha}}
    if path.startswith("git/commits/"):
      sha=path[len("git/commits/"):]
      tree=self.git("rev-parse",sha+"^{tree}").decode().strip()
      return {"tree":{"sha":tree}}
    if path.startswith("git/trees/"):
      raw=self.git("ls-tree","-z",path[len("git/trees/"):])
      entries=[]
      for line in raw.split(b"\0"):
        if not line:
          continue
        spec,name=line.split(b"\t",1)
        mode,kind,sha=spec.decode().split(" ")
        entries.append({
          "path":name.decode(),"mode":mode,"type":kind,"sha":sha})
      return {"tree":entries}
    if path.startswith("git/blobs/"):
      raw=self.git("cat-file","blob",path[len("git/blobs/"):])
      if self.forge_blob:
        raw=b'{"forged":true}'
      return {"encoding":"base64","content":base64.b64encode(raw).decode()}
    raise AssertionError("unexpected provider method "+path)


class SharedLifecycleTests(unittest.TestCase):
  def setUp(self):
    self.case=CanonicalLifecycleTests(
      "test_real_canonical_store_completed_after_retirement_promotion")
    self.case.setUp()
    self.root=self.case.root
    self.git("config","user.name","Isolated #109 fixture")
    self.git("config","user.email","fixture@example.invalid")
    self.completed=self.case.invoke()
    self.provider=GitReadOnlyProvider(self.root)

  def tearDown(self):
    self.case.tearDown()

  def git(self,*args):
    subprocess.run(["git","-C",str(self.root),*args],check=True,
                   capture_output=True)

  def publish(self):
    self.git("checkout","-qb","authority-109")
    self.git("add","-f",".repoworkflow/state")
    self.git("commit","-qm","fixture: commit exact canonical #583 records")

  def verify(self,**changes):
    args=dict(
      backend=self.provider,state_branch="authority-109",
      local_store=self.case.store,issue=123,
      completion=self.completed)
    return verify_shared_completion(**{**args,**changes})

  def test_canonical_records_durably_committed_and_re_read(self):
    self.publish()
    proof=self.verify()
    self.assertIsInstance(proof,SharedLifecycleEvidence)
    self.assertEqual(proof.issue,123)
    self.assertEqual(proof.revision,3)
    self.assertEqual(proof.operation_id,self.completed.operation_id)
    self.assertEqual(proof.accepted_sha,self.completed.terminal.accepted_sha)
    self.assertEqual(len(proof.lifecycle_digest),64)
    self.assertEqual(len(proof.intent_digest),64)
    self.assertEqual(self.provider.ref_reads,2)

  def test_local_completed_files_not_remote_is_never_done(self):
    with self.assertRaises(SharedLifecycleError):
      self.verify()
    self.assertEqual(self.case.store.read(123).lifecycle.state,"completed")

  def test_wrong_or_nonexistent_authority_ref_denied(self):
    self.publish()
    for branch in ("other-state","../traversal","/untrusted"):
      with self.subTest(branch=branch):
        with self.assertRaises(SharedLifecycleError):
          self.verify(state_branch=branch)

  def test_remote_state_ref_moved_during_readback_denied(self):
    self.publish()
    self.provider.move_on_second_ref=True
    with self.assertRaisesRegex(SharedLifecycleError,"changed"):
      self.verify()
    self.assertEqual(self.provider.ref_reads,2)

  def test_forged_blob_does_not_certify_remote_records(self):
    self.publish()
    self.provider.forge_blob=True
    with self.assertRaisesRegex(SharedLifecycleError,"blob invalid"):
      self.verify()

  def test_incorrect_completion_revision_cannot_be_promoted(self):
    self.publish()
    bad=replace(self.completed,lifecycle={
      **self.completed.lifecycle,"revision":2})
    with self.assertRaisesRegex(SharedLifecycleError,"identity differs"):
      self.verify(completion=bad)

  def test_foreign_operation_id_rejected_without_remote_reads(self):
    self.publish()
    bad=replace(self.completed,operation_id="other-operation")
    with self.assertRaisesRegex(SharedLifecycleError,"identity differs"):
      self.verify(completion=bad)
    self.assertEqual(self.provider.ref_reads,0)


if __name__=="__main__":
  unittest.main()
