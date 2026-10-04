import unittest

from repo_workflow.issue_test_contract import (
  IssueTest,
  IssueTestContract,
  render_ticket_test_section,
)
from repo_workflow.issue_test_sync import (
  IssueTestSyncError,
  admit_ticket_tests,
  compare_ticket_tests,
  import_ticket_tests,
)


class IssueTestSyncTests(unittest.TestCase):
  def contract(self, body="assert True\n", trust="repository"):
    return IssueTestContract(
      issue=255,
      tests=(IssueTest("python", body),),
      trust=trust,
    )

  def ticket(self, contract):
    return render_ticket_test_section(contract)

  def test_identical_round_trip_is_idempotent_and_preserves_repository_trust(self):
    repository = self.contract()
    imported = import_ticket_tests(255, self.ticket(repository), repository)

    self.assertIs(imported, repository)
    self.assertEqual(compare_ticket_tests(255, self.ticket(repository), repository), "match")
    self.assertEqual(imported.trust, "repository")

  def test_ticket_only_import_is_untrusted(self):
    imported = import_ticket_tests(255, self.ticket(self.contract()), None)

    self.assertIsNotNone(imported)
    self.assertEqual(imported.trust, "ticket-proposed")

  def test_differing_ticket_code_fails_closed_by_default(self):
    repository = self.contract("assert True\n")
    ticket = self.ticket(self.contract("assert False\n"))

    with self.assertRaisesRegex(IssueTestSyncError, "conflict"):
      import_ticket_tests(255, ticket, repository)
    self.assertEqual(compare_ticket_tests(255, ticket, repository), "conflict")

  def test_explicit_replace_still_imports_as_untrusted(self):
    repository = self.contract("assert True\n")
    ticket = self.ticket(self.contract("assert False\n"))

    imported = import_ticket_tests(
      255,
      ticket,
      repository,
      replace_conflict=True,
    )
    self.assertEqual(imported.tests[0].body, "assert False\n")
    self.assertEqual(imported.trust, "ticket-proposed")

  def test_explicit_admission_is_separate_from_import(self):
    proposed = import_ticket_tests(255, self.ticket(self.contract()), None)
    admitted = admit_ticket_tests(proposed)

    self.assertEqual(proposed.trust, "ticket-proposed")
    self.assertEqual(admitted.trust, "admitted")
    self.assertEqual(admitted.tests, proposed.tests)

  def test_repository_contract_cannot_be_admitted_as_if_ticket_proposed(self):
    with self.assertRaisesRegex(IssueTestSyncError, "only ticket-proposed"):
      admit_ticket_tests(self.contract())

  def test_missing_ticket_section_does_not_delete_repository_contract(self):
    repository = self.contract()
    imported = import_ticket_tests(255, "ordinary ticket prose", repository)

    self.assertIs(imported, repository)
    self.assertEqual(
      compare_ticket_tests(255, "ordinary ticket prose", repository),
      "repository-only",
    )


if __name__ == "__main__":
  unittest.main()
