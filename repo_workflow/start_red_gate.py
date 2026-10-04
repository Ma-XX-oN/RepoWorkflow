from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .issue_test_contract import IssueTestContract, IssueTestContractError, IssueTestContractStore
from .issue_test_runner import IssueTestResult, run_issue_tests
from .start_state import StartState, StartStateStore

@dataclass(frozen=True)
class RedGateResult:
  state: str
  results: tuple[IssueTestResult,...]

def run_red_gate(root:Path,issue:int)->RedGateResult:
  try: contract=IssueTestContractStore(root).read(issue)
  except IssueTestContractError as error:
    if "record is missing:" in str(error):
      StartStateStore(root).write(StartState(issue,"implement"))
      return RedGateResult("implement",())
    raise
  results=run_issue_tests(root,contract)
  errors=[x for x in results if x.status=="error"]
  greens=[x for x in results if x.status=="green"]
  if errors:
    StartStateStore(root).write(StartState(issue,"start-failed","preliminary executable-test runner error"))
    return RedGateResult("start-failed",results)
  if greens:
    StartStateStore(root).write(StartState(issue,"start-failed","RED non-compliance: preliminary test unexpectedly GREEN"))
    return RedGateResult("start-failed",results)
  StartStateStore(root).write(StartState(issue,"implement"))
  return RedGateResult("implement",results)
