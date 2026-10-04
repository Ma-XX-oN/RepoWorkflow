import unittest

from repo_workflow.issue_test_contract import IssueTest, IssueTestContract
from repo_workflow.issue_test_policy import MAX_INLINE_TESTS, MAX_TEST_BODY_BYTES, IssueTestPolicyError, review_ticket_test_changes, validate_inline_test_limits

class IssueTestPolicyTests(unittest.TestCase):
  def contract(self, tests, trust="repository"):
    return IssueTestContract(issue=264, tests=tuple(tests), trust=trust)

  def test_boundary_body_size_is_allowed(self):
    validate_inline_test_limits(self.contract((IssueTest("python", "x" * MAX_TEST_BODY_BYTES),)))

  def test_body_over_limit_is_rejected(self):
    body = "x" * (MAX_TEST_BODY_BYTES + 1)
    with self.assertRaisesRegex(IssueTestPolicyError, "exceeds"):
      validate_inline_test_limits(self.contract((IssueTest("python", body),)))
    self.assertEqual(len(body), MAX_TEST_BODY_BYTES + 1)

  def test_limit_counts_utf8_bytes(self):
    body = "é" * ((MAX_TEST_BODY_BYTES // 2) + 1)
    with self.assertRaisesRegex(IssueTestPolicyError, "UTF-8 bytes"):
      validate_inline_test_limits(self.contract((IssueTest("python", body),)))

  def test_test_count_is_bounded(self):
    tests = tuple(IssueTest("python", "assert True\n") for _ in range(MAX_INLINE_TESTS + 1))
    with self.assertRaisesRegex(IssueTestPolicyError, "count exceeds"):
      validate_inline_test_limits(self.contract(tests))

  def test_review_diff_warns_and_names_accept_command(self):
    old = self.contract((IssueTest("bash", "test -f old\n"),))
    new = self.contract((IssueTest("python", "assert new_value\n"),), "ticket-proposed")
    text = review_ticket_test_changes(old, new)
    self.assertIn("WARNING:", text)
    self.assertIn("-test -f old", text)
    self.assertIn("+assert new_value", text)
    self.assertTrue(text.rstrip().endswith("rwf tests accept"))

if __name__ == "__main__":
  unittest.main()
