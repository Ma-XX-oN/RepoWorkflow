from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .state_store import StateStoreError, WriterIdentity, durable_store


TESTS_KEY_PREFIX = "issues/tests"
SCHEMA_VERSION = 1
SECTION_START = "<!-- rwf:issue-tests:v1 -->"
SECTION_END = "<!-- /rwf:issue-tests -->"
SUPPORTED_LANGUAGES = frozenset({"bash", "python"})


class IssueTestContractError(RuntimeError):
  """Raised when an executable issue-test contract is invalid."""


@dataclass(frozen=True)
class IssueTest:
  language: str
  body: str


@dataclass(frozen=True)
class IssueTestContract:
  issue: int
  tests: tuple[IssueTest, ...]
  trust: str
  revision: int = 0


class IssueTestContractStore:
  """Durable executable-test contract reader/writer for one issue."""

  def __init__(self, repository_root: Path):
    self.root = Path(repository_root).resolve()
    self.records = durable_store(self.root)

  def read(self, issue_number: int) -> IssueTestContract:
    issue = _positive_integer(issue_number, "issue number")
    try:
      record = self.records.read(f"{TESTS_KEY_PREFIX}/{issue}")
      value = _parse_value(record["value"])
    except (StateStoreError, ValueError) as error:
      raise IssueTestContractError(str(error)) from error
    return IssueTestContract(
      issue=value.issue,
      tests=value.tests,
      trust=value.trust,
      revision=record["revision"],
    )

  def write(
    self,
    contract: IssueTestContract,
    writer: WriterIdentity,
  ) -> IssueTestContract:
    value = _contract_value(contract)
    key = f"{TESTS_KEY_PREFIX}/{contract.issue}"
    path = (
      self.root / ".repoworkflow" / "state" / "issues" / "tests"
      / f"{contract.issue}.json"
    )
    try:
      if path.exists():
        current = self.records.read(key)
        record = self.records.replace(key, current["revision"], value, writer)
      else:
        record = self.records.create(key, value, writer)
    except StateStoreError as error:
      raise IssueTestContractError(str(error)) from error
    parsed = _parse_value(record["value"])
    return IssueTestContract(
      issue=parsed.issue,
      tests=parsed.tests,
      trust=parsed.trust,
      revision=record["revision"],
    )


def parse_ticket_test_section(
  issue_number: int,
  markdown: str,
) -> IssueTestContract | None:
  """Parse only the explicitly delimited RWF executable-test ticket section."""
  issue = _positive_integer(issue_number, "issue number")
  if not isinstance(markdown, str):
    raise IssueTestContractError("ticket Markdown must be text")
  starts = markdown.count(SECTION_START)
  ends = markdown.count(SECTION_END)
  if starts == 0 and ends == 0:
    return None
  if starts != 1 or ends != 1:
    raise IssueTestContractError("ticket executable-test section is ambiguous")
  start = markdown.index(SECTION_START) + len(SECTION_START)
  end = markdown.index(SECTION_END)
  if end < start:
    raise IssueTestContractError("ticket executable-test section is malformed")
  section = markdown[start:end].strip()
  tests = _parse_fences(section)
  return IssueTestContract(issue=issue, tests=tests, trust="ticket-proposed")


def render_ticket_test_section(contract: IssueTestContract) -> str:
  """Render the structured ticket section without serializing trust authority."""
  _contract_value(contract)
  fences = []
  for test in contract.tests:
    fences.append(f"```{test.language}\n{test.body}```")
  body = "\n\n".join(fences)
  return f"{SECTION_START}\n{body}\n{SECTION_END}"


def _parse_fences(section: str) -> tuple[IssueTest, ...]:
  if not section:
    return ()
  pattern = re.compile(r"(?ms)^\\`\\`\\`([A-Za-z0-9_-]+)\\n(.*?)^\\`\\`\\`[ \\t]*$")
  tests = []
  position = 0
  for match in pattern.finditer(section):
    between = section[position:match.start()]
    if between.strip():
      raise IssueTestContractError(
        "structured executable-test section contains non-fence content"
      )
    language = match.group(1)
    body = match.group(2)
    _validate_test(language, body)
    tests.append(IssueTest(language=language, body=body))
    position = match.end()
  if section[position:].strip():
    raise IssueTestContractError(
      "structured executable-test section contains malformed fence content"
    )
  return tuple(tests)


def _parse_value(value: dict) -> IssueTestContract:
  if not isinstance(value, dict) or set(value) != {
    "schema_version", "issue", "trust", "tests"
  }:
    raise ValueError("issue test contract has unsupported fields")
  if value["schema_version"] != SCHEMA_VERSION:
    raise ValueError("unsupported issue test contract schema version")
  issue = _positive_integer(value["issue"], "issue test contract issue")
  trust = value["trust"]
  if trust not in {"repository", "ticket-proposed", "admitted"}:
    raise ValueError("unsupported issue test trust state")
  raw_tests = value["tests"]
  if not isinstance(raw_tests, list):
    raise ValueError("issue test contract tests must be an array")
  tests = []
  for raw in raw_tests:
    if not isinstance(raw, dict) or set(raw) != {"language", "body"}:
      raise ValueError("issue test entry has unsupported fields")
    language = raw["language"]
    body = raw["body"]
    _validate_test(language, body)
    tests.append(IssueTest(language=language, body=body))
  return IssueTestContract(issue=issue, tests=tuple(tests), trust=trust)


def _contract_value(contract: IssueTestContract) -> dict:
  if not isinstance(contract, IssueTestContract):
    raise IssueTestContractError("invalid issue test contract")
  issue = _positive_integer(contract.issue, "issue test contract issue")
  if contract.trust not in {"repository", "ticket-proposed", "admitted"}:
    raise IssueTestContractError("unsupported issue test trust state")
  tests = []
  for test in contract.tests:
    if not isinstance(test, IssueTest):
      raise IssueTestContractError("invalid issue test entry")
    _validate_test(test.language, test.body)
    tests.append({"language": test.language, "body": test.body})
  return {
    "schema_version": SCHEMA_VERSION,
    "issue": issue,
    "trust": contract.trust,
    "tests": tests,
  }


def _validate_test(language, body) -> None:
  if language not in SUPPORTED_LANGUAGES:
    raise IssueTestContractError(
      f"unsupported executable-test language: {language!r}"
    )
  if not isinstance(body, str) or not body:
    raise IssueTestContractError("executable-test body must be non-empty text")


def _positive_integer(value, label: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise ValueError(f"{label} must be a positive integer")
  return value
