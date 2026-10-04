from pathlib import Path
import unittest

from repo_workflow.issue_test_review import _replace_section
from repo_workflow.issue_test_contract import SECTION_START, SECTION_END
from repo_workflow.command_grammar import Context, parse_tokens
from repo_workflow.public_commands import COMMANDS

class IssueTestReviewUnitTests(unittest.TestCase):
  def test_replace_section_preserves_surrounding_ticket_prose(self):
    old=f"before\n{SECTION_START}\nold\n{SECTION_END}\nafter\n"
    new=f"{SECTION_START}\nnew\n{SECTION_END}"
    self.assertEqual(_replace_section(old,new),f"before\n{new}\nafter\n")

  def test_insert_section_preserves_existing_body(self):
    section=f"{SECTION_START}\nx\n{SECTION_END}"
    self.assertEqual(_replace_section("prose",section),f"prose\n{section}\n")

  def test_public_review_grammar_includes_sync_views_accept_and_git_tail(self):
    context=Context(Path("."), legal_only=False)
    for words in (["tests","sync"],["tests","view"],["tests","view","new"],["tests","view","old"],["tests","accept","new"],["tests","accept","old"],["tests","diff"],["tests","diff","--word-diff"]):
      self.assertEqual(parse_tokens(COMMANDS,context,words),tuple(words))

  def test_bare_accept_is_not_public_grammar(self):
    context=Context(Path("."), legal_only=False)
    from repo_workflow.command_grammar import CommandGrammarError
    with self.assertRaises(CommandGrammarError):
      parse_tokens(COMMANDS,context,["tests","accept"])

if __name__ == "__main__": unittest.main()
