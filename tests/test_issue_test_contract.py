from pathlib import Path
import tempfile
import unittest

from repo_workflow.issue_test_contract import (
  IssueTest,
  IssueTestContract,
  IssueTestContractError,
  IssueTestContractStore,
  SECTION_END,
  SECTION_START,
  parse_ticket_test_section,
  render_ticket_test_section,
)
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class IssueTestContractTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent-a", "session-1")

  def tearDown(self):
    self.temp.cleanup()

  def test_store_round_trip_preserves_order_language_body_and_trust(self):
    contract = IssueTestContract(
      issue=252,
      tests=(
        IssueTest("bash", "test -f PARENT_BRANCH_WORKFLOW.md\n"),
        IssueTest("python", "assert 1 + 1 == 2\n"),
      ),
      trust="repository",
    )
    written = IssueTestContractStore(self.root).write(contract, self.writer)
    restarted = IssueTestContractStore(self.root).read(252)

    self.assertEqual(restarted.issue, 252)
    self.assertEqual(restarted.tests, contract.tests)
    self.assertEqual(restarted.trust, "repository")
    self.assertEqual(restarted.revision, written.revision)

  def test_ticket_parser_ignores_ordinary_code_fences(self):
    markdown = "Example only:\n\n```bash\nrm -rf example\n```\n"
    self.assertIsNone(parse_ticket_test_section(252, markdown))

  def test_ticket_round_trip_preserves_executable_meaning(self):
    contract = IssueTestContract(
      issue=252,
      tests=(
        IssueTest("bash", "test -f README.md\n"),
        IssueTest("python", "assert True\n"),
      ),
      trust="repository",
    )

    rendered = render_ticket_test_section(contract)
    parsed = parse_ticket_test_section(252, rendered)

    self.assertIsNotNone(parsed)
    self.assertEqual(parsed.tests, contract.tests)
    self.assertEqual(parsed.trust, "ticket-proposed")

  def test_ticket_parser_rejects_unknown_language(self):
    markdown = (
      f"{SECTION_START}\n"
      "```ruby\nputs 'hello'\n```\n"
      f"{SECTION_END}"
    )
    with self.assertRaisesRegex(
      IssueTestContractError, "unsupported executable-test language"
    ):
      parse_ticket_test_section(252, markdown)

  def test_ticket_parser_rejects_malformed_or_ambiguous_sections(self):
    with self.assertRaisesRegex(IssueTestContractError, "ambiguous"):
      parse_ticket_test_section(
        252,
        f"{SECTION_START}\n{SECTION_START}\n{SECTION_END}",
      )
    with self.assertRaisesRegex(IssueTestContractError, "malformed"):
      parse_ticket_test_section(252, f"{SECTION_END}\n{SECTION_START}")

  def test_structured_section_rejects_non_fence_content(self):
    markdown = (
      f"{SECTION_START}\n"
      "This text is not executable-test structure.\n"
      "```bash\ntest -f README.md\n```\n"
      f"{SECTION_END}"
    )
    with self.assertRaisesRegex(IssueTestContractError, "non-fence content"):
      parse_ticket_test_section(252, markdown)


if __name__ == "__main__":
  unittest.main()
