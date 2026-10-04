from __future__ import annotations

import json
from pathlib import Path

from .issue_test_contract import IssueTestContractError, IssueTestContractStore
from .issue_test_runner import IssueTestRunnerError, run_issue_tests


def verify_issue_tests(repository_root: Path, issue_number: int) -> int:
  """Execute admitted executable tests for one issue and print results."""
  try:
    contract = IssueTestContractStore(repository_root).read(issue_number)
    results = run_issue_tests(repository_root, contract)
  except (IssueTestContractError, IssueTestRunnerError) as error:
    print(json.dumps({
      "issue": issue_number,
      "status": "error",
      "error": str(error),
    }, separators=(",", ":")))
    return 2

  status = "green"
  if any(result.status == "error" for result in results):
    status = "error"
  elif any(result.status == "red" for result in results):
    status = "red"
  print(json.dumps({
    "issue": issue_number,
    "status": status,
    "tests": [
      {
        "index": result.index,
        "language": result.language,
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
      }
      for result in results
    ],
  }, separators=(",", ":")))
  return {"green": 0, "red": 1, "error": 2}[status]
