from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys

from .issue_test_contract import IssueTest, IssueTestContract


class IssueTestRunnerError(RuntimeError):
  """Raised when an executable issue-test contract is not eligible to run."""


@dataclass(frozen=True)
class IssueTestResult:
  index: int
  language: str
  status: str
  exit_code: int | None
  stdout: str
  stderr: str


def run_issue_tests(
  repository_root: Path,
  contract: IssueTestContract,
  timeout_seconds: float = 30.0,
) -> tuple[IssueTestResult, ...]:
  """Run an admitted issue-test contract in declared order."""
  root = Path(repository_root).resolve()
  if contract.trust not in {"repository", "admitted"}:
    raise IssueTestRunnerError(
      f"issue {contract.issue} executable tests are not admitted for execution"
    )
  if timeout_seconds <= 0:
    raise IssueTestRunnerError("test timeout must be positive")

  results = []
  for index, test in enumerate(contract.tests, start=1):
    results.append(_run_test(root, index, test, timeout_seconds))
  return tuple(results)


def _run_test(
  root: Path,
  index: int,
  test: IssueTest,
  timeout_seconds: float,
) -> IssueTestResult:
  command = _command(test)
  if command is None:
    return IssueTestResult(
      index=index,
      language=test.language,
      status="error",
      exit_code=None,
      stdout="",
      stderr=f"evaluator unavailable for {test.language}",
    )
  try:
    completed = subprocess.run(
      command,
      cwd=root,
      capture_output=True,
      text=True,
      timeout=timeout_seconds,
      check=False,
    )
  except (OSError, subprocess.TimeoutExpired) as error:
    return IssueTestResult(
      index=index,
      language=test.language,
      status="error",
      exit_code=None,
      stdout=getattr(error, "stdout", "") or "",
      stderr=getattr(error, "stderr", "") or str(error),
    )
  return IssueTestResult(
    index=index,
    language=test.language,
    status="green" if completed.returncode == 0 else "red",
    exit_code=completed.returncode,
    stdout=completed.stdout,
    stderr=completed.stderr,
  )


def _command(test: IssueTest) -> list[str] | None:
  if test.language == "python":
    return [sys.executable, "-c", test.body]
  if test.language == "bash":
    bash = shutil.which("bash")
    if bash is None:
      return None
    return [bash, "-c", test.body]
  return None
