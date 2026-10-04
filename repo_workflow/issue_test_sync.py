from __future__ import annotations

from dataclasses import replace

from .issue_test_contract import (
  IssueTestContract,
  IssueTestContractError,
  parse_ticket_test_section,
)


class IssueTestSyncError(RuntimeError):
  """Raised when executable-test synchronization cannot proceed safely."""


def compare_ticket_tests(
  issue_number: int,
  markdown: str,
  repository_contract: IssueTestContract | None,
) -> str:
  """Compare executable meaning without changing either representation."""
  ticket = parse_ticket_test_section(issue_number, markdown)
  if repository_contract is None and ticket is None:
    return "match"
  if repository_contract is None:
    return "ticket-only"
  if ticket is None:
    return "repository-only"
  return "match" if repository_contract.tests == ticket.tests else "conflict"


def import_ticket_tests(
  issue_number: int,
  markdown: str,
  repository_contract: IssueTestContract | None,
  *,
  replace_conflict: bool = False,
) -> IssueTestContract | None:
  """Prepare ticket tests for storage without granting execution trust."""
  ticket = parse_ticket_test_section(issue_number, markdown)
  status = compare_ticket_tests(issue_number, markdown, repository_contract)
  if status in {"match", "repository-only"}:
    return repository_contract
  if status == "ticket-only":
    return ticket
  if not replace_conflict:
    raise IssueTestSyncError(
      "ticket executable tests conflict with repository executable tests"
    )
  return ticket


def admit_ticket_tests(contract: IssueTestContract) -> IssueTestContract:
  """Explicitly admit a previously imported ticket-proposed contract."""
  if contract.trust != "ticket-proposed":
    raise IssueTestSyncError(
      "only ticket-proposed executable tests can cross the admission boundary"
    )
  return replace(contract, trust="admitted", revision=0)


def require_ticket_safe_export(contract: IssueTestContract) -> None:
  """Validate that a contract can be rendered without exporting trust authority."""
  if contract.trust not in {"repository", "admitted", "ticket-proposed"}:
    raise IssueTestContractError("unsupported issue test trust state")
