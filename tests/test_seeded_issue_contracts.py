from pathlib import Path
import unittest

from repo_workflow.issue_test_contract import IssueTestContractStore
from repo_workflow.issue_test_policy import validate_inline_test_limits

class SeededLifecycleContractsTests(unittest.TestCase):
  def test_seeded_contracts_are_repository_trusted_and_within_inline_limits(self):
    root=Path(__file__).resolve().parents[1]
    store=IssueTestContractStore(root)
    for issue in (230,231,233,234,235):
      contract=store.read(issue)
      self.assertEqual(contract.trust,"repository")
      self.assertEqual(len(contract.tests),1)
      validate_inline_test_limits(contract)

  def test_232_has_no_placeholder_contract(self):
    root=Path(__file__).resolve().parents[1]
    self.assertFalse((root/".repoworkflow/state/issues/tests/232.json").exists())

if __name__=="__main__": unittest.main()
