"""Generic remote dispatch preserves the normal public command arguments."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.public_cli import handle_public
from repo_workflow.command_grammar import Context, parse_tokens, completion_items
from repo_workflow.public_commands import COMMANDS


class GenericRemoteDispatchTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    subprocess.run(["git", "init", "-q", "-b", "issue-660-fixture"],
                   cwd=self.root, capture_output=True, check=True)

  def test_non_test_read_only_uses_same_remote_submission(self):
    with patch("repo_workflow.public_cli.submit_remote", return_value=0) as remote:
      self.assertEqual(handle_public(
        self.root, ["issue", "info", "--remote"], engine_root=self.root,
      ), 0)
    remote.assert_called_once_with(
      self.root, ["issue", "info", "--remote"], intervals=None,
    )

  def test_non_test_mutating_uses_same_remote_submission(self):
    with patch("repo_workflow.public_cli.submit_remote", return_value=0) as remote:
      self.assertEqual(handle_public(
        self.root, ["settings", "color", "always", "--remote", "--poll", "0"],
        engine_root=self.root,
      ), 0)
    remote.assert_called_once_with(
      self.root, ["settings", "color", "always", "--remote"], intervals=(0.0,),
    )

  def test_generic_remote_is_in_the_authoritative_grammar(self):
    context = Context(self.root, legal_only=False)
    examples = (
      ("issue", "info"),
      ("issue", "64", "dependency", "from-tickets"),
      ("issue", "64", "dependency", "to-tickets"),
      ("settings", "color", "always"),
      ("lanes", "clear"),
      ("workspace", "list"),
      ("test", "RED"),
    )
    for words in examples:
      with self.subTest(command=words):
        self.assertEqual(
          parse_tokens(COMMANDS, context, [*words, "--remote"]),
          (*words, "--remote"),
        )
        # RED's completion deliberately reports a missing selection catalogue
        # before returning switches; its parser still accepts the transport.
        if words != ("test", "RED"):
          self.assertIn(
            "--remote",
            {item.token for item in completion_items(
              COMMANDS, context, [*words, "--r"],
            )},
          )
    with self.assertRaisesRegex(Exception, "invalid command token"):
      parse_tokens(COMMANDS, context, ["remote-status", "--remote"])

  def test_malformed_remote_switch_fails_before_submission(self):
    with patch("repo_workflow.public_cli.submit_remote") as remote:
      with self.assertRaisesRegex(Exception, "remote must end"):
        handle_public(
          self.root, ["issue", "info", "--remote", "garbage"],
          engine_root=self.root,
        )
    remote.assert_not_called()


if __name__ == "__main__":
  unittest.main()
