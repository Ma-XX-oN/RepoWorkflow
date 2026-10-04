from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.ticket_write_adapter import TicketWriteError, body_digest, replace_issue_body
from tests.support import RepoFixture

class TicketWriteAdapterTests(unittest.TestCase):
  def fixture(self, root, script_body):
    RepoFixture(root)
    script = root / "scripts" / "ticket.py"
    script.write_text(script_body, encoding="utf-8")
    return {"ticketCommand": [sys.executable, str(script)]}

  def test_exact_confirmed_replace(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"; root.mkdir()
      body = "new body\n"; digest = body_digest(body)
      config = self.fixture(root, "import json, pathlib, sys\nbody=pathlib.Path(sys.argv[-1]).read_text()\nprint(json.dumps({'schema_version':1,'number':7,'body_digest':__import__('hashlib').sha256(body.encode()).hexdigest()}))\n")
      self.assertEqual(replace_issue_body(root, config, 7, "0" * 64, body)["body_digest"], digest)

  def test_failure_and_unconfirmed_write_fail_closed(self):
    cases = [("raise SystemExit(7)\n", "adapter failed"), ("print('{}')\n", "unconfirmed")]
    for script, message in cases:
      with self.subTest(message=message), tempfile.TemporaryDirectory() as td:
        root=Path(td)/"repo"; root.mkdir(); config=self.fixture(root, script)
        with self.assertRaisesRegex(TicketWriteError, message):
          replace_issue_body(root, config, 7, "0" * 64, "x")

  def test_missing_configuration_fails(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td)/"repo"; root.mkdir(); RepoFixture(root)
      with self.assertRaisesRegex(TicketWriteError, "not configured"):
        replace_issue_body(root, {}, 7, "0" * 64, "x")

if __name__ == "__main__": unittest.main()
