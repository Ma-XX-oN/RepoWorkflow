from __future__ import annotations

import difflib

from .issue_test_contract import IssueTestContract, render_ticket_test_section

MAX_INLINE_TESTS = 8
MAX_TEST_BODY_BYTES = 4096
MAX_TEST_SECTION_BYTES = 16384

class IssueTestPolicyError(RuntimeError):
  pass

def validate_inline_test_limits(contract: IssueTestContract) -> None:
  if len(contract.tests) > MAX_INLINE_TESTS:
    raise IssueTestPolicyError(f"inline executable-test count exceeds {MAX_INLINE_TESTS}")
  for index, test in enumerate(contract.tests, start=1):
    size = len(test.body.encode("utf-8"))
    if size > MAX_TEST_BODY_BYTES:
      raise IssueTestPolicyError(f"inline executable test {index} exceeds {MAX_TEST_BODY_BYTES} UTF-8 bytes")
  section_size = len(render_ticket_test_section(contract).encode("utf-8"))
  if section_size > MAX_TEST_SECTION_BYTES:
    raise IssueTestPolicyError(f"structured executable-test section exceeds {MAX_TEST_SECTION_BYTES} UTF-8 bytes")

def review_ticket_test_changes(repository_contract: IssueTestContract, ticket_contract: IssueTestContract) -> str:
  validate_inline_test_limits(repository_contract)
  validate_inline_test_limits(ticket_contract)
  before = render_ticket_test_section(repository_contract).splitlines(keepends=True)
  after = render_ticket_test_section(ticket_contract).splitlines(keepends=True)
  diff = "".join(difflib.unified_diff(before, after, fromfile=f"repository issue #{repository_contract.issue} tests", tofile=f"ticket issue #{ticket_contract.issue} tests"))
  return (f"Executable-test changes for issue #{repository_contract.issue}:\n"
          "WARNING: accepting the ticket version permits this code to execute through its declared evaluator.\n"
          f"{diff}\nReview the complete proposal with: rwf tests view\n"
          "Accept exactly this reviewed proposal with: rwf tests accept\n")
