from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.issue_test_contract import IssueTest, IssueTestContract, IssueTestContractStore
from repo_workflow.start_red_gate import run_red_gate
from repo_workflow.start_state import StartStateStore
from repo_workflow.state_store import WriterIdentity

class StartRedGateTests(unittest.TestCase):
  def repo(self):
    td=tempfile.TemporaryDirectory(); root=Path(td.name)
    subprocess.run(["git","init","-b","main"],cwd=root,check=True,capture_output=True)
    subprocess.run(["git","config","user.email","test@example.invalid"],cwd=root,check=True)
    subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
    return td,root
  def write(self,root,body):
    IssueTestContractStore(root).write(IssueTestContract(issue=7,tests=(IssueTest("python",body),),trust="repository"),WriterIdentity("seed","seed"))
  def test_all_red_enters_implement(self):
    td,root=self.repo()
    try:
      self.write(root,"raise SystemExit(1)\n")
      with patch.dict(os.environ,{"RWF_WRITER_ID":"a","RWF_SESSION_ID":"s"}):
        result=run_red_gate(root,7)
      self.assertEqual(result.state,"implement")
      self.assertEqual(StartStateStore(root).read(7).state,"implement")
    finally: td.cleanup()
  def test_any_green_enters_start_failed(self):
    td,root=self.repo()
    try:
      self.write(root,"assert True\n")
      with patch.dict(os.environ,{"RWF_WRITER_ID":"a","RWF_SESSION_ID":"s"}):
        result=run_red_gate(root,7)
      self.assertEqual(result.state,"start-failed")
      self.assertIn("RED non-compliance",StartStateStore(root).read(7).detail)
    finally: td.cleanup()

if __name__=="__main__": unittest.main()
