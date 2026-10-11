"""Standalone black-box tests of canonical committed CI invocation semantics."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from repo_workflow.ci_invocation import verify_invocation

class CommittedMarkerIntegrityTests(unittest.TestCase):
  def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    self.root=Path(self.temp.name)
    self.git('init','-q')
    self.git('config','user.name','Audit')
    self.git('config','user.email','audit@example.invalid')
    (self.root/'source.txt').write_text('source\n')
    self.git('add','source.txt');self.git('commit','-qm','source')
    self.parent=self.git('rev-parse','HEAD')
    marker=self.root/'.ci/run';marker.parent.mkdir();marker.write_text('GREEN-testing '+self.parent+'\n')
    self.git('add','.ci/run');self.git('commit','-qm','request GREEN')
    self.marker=marker
  def git(self,*args):
    return subprocess.check_output(['git','-C',str(self.root),*args],text=True).strip()
  def test_uncommitted_stage_must_not_replace_committed_request(self):
    self.marker.write_text('RED-testing '+self.parent+'\n')
    verified=verify_invocation(self.root)
    self.assertEqual(verified.stage,'GREEN-testing',
      'Committed GREEN marker was substituted by uncommitted RED marker')
  def test_uncommitted_invalid_sha_must_not_replace_committed_request(self):
    self.marker.write_text('GREEN-testing '+'f'*40+'\n')
    verified=verify_invocation(self.root)
    self.assertEqual((verified.stage,verified.previous_tip),('GREEN-testing',self.parent))

if __name__=='__main__':
  unittest.main(verbosity=2)
