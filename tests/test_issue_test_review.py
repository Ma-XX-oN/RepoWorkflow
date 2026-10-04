from pathlib import Path
import unittest

from repo_workflow.issue_test_review import _replace_section
from repo_workflow.issue_test_contract import SECTION_START, SECTION_END

class IssueTestReviewUnitTests(unittest.TestCase):
  def test_replace_section_preserves_surrounding_ticket_prose(self):
    old=f"before\n{SECTION_START}\nold\n{SECTION_END}\nafter\n"
    new=f"{SECTION_START}\nnew\n{SECTION_END}"
    self.assertEqual(_replace_section(old,new),f"before\n{new}\nafter\n")

  def test_insert_section_preserves_existing_body(self):
    section=f"{SECTION_START}\nx\n{SECTION_END}"
    self.assertEqual(_replace_section("prose",section),f"prose\n{section}\n")

if __name__ == "__main__": unittest.main()
