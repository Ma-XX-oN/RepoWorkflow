from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.issue_start import IssueStartError, start_issue
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity


class IssueStartTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=self.repo, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=self.repo,
      check=True,
    )
    subprocess.run(
      ["git", "config", "user.name", "Test"],
      cwd=self.repo,
      check=True,
    )
    (self.repo / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    subprocess.run(["git", "add", "VERSION"], cwd=self.repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=self.repo, check=True)
    self._write_adapters()
    RelationshipStore(self.repo).create(
      RelationshipGraph(issues={
        "7": IssueRelationships("Issue 7", ()),
      }),
      WriterIdentity("planner", "planning-session"),
    )
    self.config = {
      "versionCommand": [sys.executable, str(self.version_adapter)],
      "infoCommand": [sys.executable, str(self.info_adapter)],
    }

  def tearDown(self):
    self.temp.cleanup()

  def _write_adapters(self):
    self.version_adapter = Path(self.temp.name) / "version.py"
    self.version_adapter.write_text(
      "from pathlib import Path\n"
      "import sys\n"
      "path = Path('VERSION')\n"
      "value = path.read_text().strip()\n"
      "args = sys.argv[1:]\n"
      "if args:\n"
      "  if args[:2] != ['task', '--issue']:\n"
      "    raise SystemExit(2)\n"
      "  major, minor, patch = value.split('.')\n"
      "  value = f'{major}.{minor}.{patch}-issue.{args[2]}.0.1'\n"
      "  path.write_text(value + '\\n')\n"
      "print(value)\n",
      encoding="utf-8",
    )
    self.info_adapter = Path(self.temp.name) / "info.py"
    self.info_adapter.write_text(
      "import json\n"
      "import sys\n"
      "number = int(sys.argv[-1])\n"
      "print(json.dumps({'schema_version': 1, 'number': number, "
      "'title': 'Issue', 'state': 'open', 'link': f'https://example.invalid/issues/{number}'}))\n",
      encoding="utf-8",
    )

  def test_start_materializes_all_canonical_state(self):
    with patch.dict(
      os.environ,
      {
        "RWF_WRITER_ID": "agent-a",
        "RWF_SESSION_ID": "session-1",
      },
      clear=False,
    ):
      result = start_issue(self.repo, 7, config=self.config)

    self.assertEqual(result.issue, "7")
    self.assertEqual(result.version, "1.2.3-issue.7.0.1")
    self.assertEqual(result.branch, "issue-7")
    self.assertEqual(
      subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=self.repo,
        check=True,
        capture_output=True,
        text=True,
      ).stdout.strip(),
      "issue-7",
    )
    self.assertEqual(result.lifecycle_revision, 0)

  def test_committed_replay_is_idempotent(self):
    environment = {
      "RWF_WRITER_ID": "agent-a",
      "RWF_SESSION_ID": "session-1",
    }
    with patch.dict(os.environ, environment, clear=False):
      first = start_issue(self.repo, 7, config=self.config)
      second = start_issue(self.repo, 7, config=self.config)

    self.assertEqual(second, first)

  def test_missing_identity_fails_before_mutation(self):
    with patch.dict(os.environ, {}, clear=True):
      with self.assertRaises(Exception):
        start_issue(self.repo, 7, config=self.config)
    self.assertEqual(
      (self.repo / "VERSION").read_text(encoding="utf-8"),
      "1.2.3\n",
    )


if __name__ == "__main__":
  unittest.main()
