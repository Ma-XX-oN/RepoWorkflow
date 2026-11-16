"""Contract tests for immediate-child destination allow-lists."""

from pathlib import Path
import tempfile
import unittest

from repo_workflow.ticket_admission import (
  TicketAdmissionError, parse_policy, policy_path, ticket_allowed,
)


class TicketAdmissionTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)

  def put(self, destination, text):
    path = self.root / policy_path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

  def allowed(self, ticket, *, destination="issue-123", immediate=True):
    return ticket_allowed(self.root, destination, ticket,
      immediate_child=immediate)

  def test_absent_file_adds_no_restriction(self):
    self.assertTrue(self.allowed(124))

  def test_existing_empty_file_blocks_everyone(self):
    self.put("issue-123", "")
    self.assertFalse(self.allowed(124))

  def test_only_listed_immediate_children_pass(self):
    self.put("issue-123", "124\n125\n")
    self.assertTrue(self.allowed(124))
    self.assertFalse(self.allowed(126))
    self.assertFalse(self.allowed(124, immediate=False))

  def test_policy_is_per_destination(self):
    self.put("issue-123", "124\n")
    self.put("main", "100\n")
    self.assertTrue(self.allowed(124))
    self.assertFalse(self.allowed(124, destination="main"))

  def test_latest_policy_is_used_at_each_read(self):
    self.put("issue-123", "124\n")
    self.assertTrue(self.allowed(124))
    self.put("issue-123", "125\n")
    self.assertFalse(self.allowed(124))

  def test_invalid_lines_fail_closed(self):
    for contents in ("0\n", "124\n\n125\n", " 124\n", "124 # note\n",
        "124\n124\n", "-1\n", "12.4\n"):
      with self.subTest(contents=contents):
        self.put("issue-123", contents)
        with self.assertRaises(TicketAdmissionError):
          self.allowed(124)

  def test_unsafe_paths_rejected(self):
    for destination in ("", "../main", "main/../other", "/main",
        "main//other", "a\\b", "main space"):
      with self.subTest(destination=destination):
        with self.assertRaises(TicketAdmissionError):
          policy_path(destination)

  def test_non_integer_issue_and_untrusted_relation_rejected(self):
    with self.assertRaises(TicketAdmissionError):
      self.allowed(True)
    with self.assertRaises(TicketAdmissionError):
      ticket_allowed(self.root, "main", 1, immediate_child="yes")

  def test_parser(self):
    self.assertEqual(parse_policy(""), frozenset())
    self.assertEqual(parse_policy("124\n125\n"), frozenset((124, 125)))


if __name__ == "__main__":
  unittest.main()
