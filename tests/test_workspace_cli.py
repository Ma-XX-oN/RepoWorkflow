import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.current_work_store import CurrentWorkStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceCliTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    self.fx = RepoFixture(self.root, version="1.0.0")
    info_script = self.root / "scripts" / "info.py"
    info_script.write_text(
      "import json\n"
      "import sys\n"
      "number = int(sys.argv[-1])\n"
      "print(json.dumps({'schema_version': 1, 'number': number, "
      "'title': 'Workspace issue', 'state': 'open', 'link': f'https://example.invalid/issues/{number}'}))\n",
      encoding="utf-8",
    )
    config_path = self.root / ".ci" / "repoworkflow.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["infoCommand"] = [sys.executable, "scripts/info.py"]
    config_path.write_text(
      json.dumps(config, indent=2) + "\n",
      encoding="utf-8",
    )
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "140": IssueRelationships(
          umbrella="135",
          shared_umbrellas=(),
          depends_on=(),
          umbrella_depends_on=(),
          parent="issue-1-test",
        ),
      }),
      WriterIdentity("planner", "planning-session"),
    )
    self.fx.commit("register workspace issue")
    self.env = dict(os.environ)
    self.env["RWF_WORKER_ID"] = "agent-a"
    self.env["RWF_WRITER_ID"] = "agent-a"
    self.env["RWF_SESSION_ID"] = "chat-1"

  def tearDown(self):
    self.temp.cleanup()

  def run_rwf(self, *words: str, root: Path | None = None):
    return subprocess.run(
      [
        sys.executable,
        str(ROOT / "repo_workflow.py"),
        "--root",
        str(root or self.root),
        *words,
      ],
      capture_output=True,
      text=True,
      env=self.env,
    )

  def test_create_list_info_and_claim_lifecycle(self):
    created = self.run_rwf("workspace", "create", "140")
    self.assertEqual(created.returncode, 0, created.stderr)
    value = json.loads(created.stdout)
    self.assertEqual(value["workspace_id"], "RWF-140")
    self.assertEqual(value["issue"], 140)
    self.assertEqual(value["claim"]["status"], "available")
    worktree = Path(value["worktree_path"])
    self.assertTrue(worktree.is_dir())
    lifecycle = LifecycleStore(worktree).read(140)
    self.assertEqual(lifecycle.lifecycle.state, "active")
    current = CurrentWorkStore(worktree).read(validate_durable=True)
    self.assertEqual(current.value.current.issue, "140")
    self.assertEqual(value["branch"], "issue-140")

    listed = self.run_rwf("workspace", "list")
    self.assertEqual(listed.returncode, 0, listed.stderr)
    self.assertIn("RWF-140\tissue=140\tstatus=available", listed.stdout)

    info = self.run_rwf("workspace", "info", root=worktree)
    self.assertEqual(info.returncode, 0, info.stderr)
    self.assertEqual(json.loads(info.stdout)["workspace_id"], "RWF-140")

    claimed = self.run_rwf("workspace", "claim", "RWF-140")
    self.assertEqual(claimed.returncode, 0, claimed.stderr)
    self.assertEqual(json.loads(claimed.stdout)["revision"], 1)

    self.env["RWF_SESSION_ID"] = "chat-2"
    resumed = self.run_rwf("workspace", "resume", "RWF-140")
    self.assertEqual(resumed.returncode, 0, resumed.stderr)
    resumed_value = json.loads(resumed.stdout)
    self.assertEqual(resumed_value["revision"], 2)
    self.assertEqual(resumed_value["session_id"], "chat-2")

    released = self.run_rwf("workspace", "release", "RWF-140")
    self.assertEqual(released.returncode, 0, released.stderr)
    self.assertEqual(json.loads(released.stdout)["status"], "available")

    closed = self.run_rwf("workspace", "close", "RWF-140")
    self.assertEqual(closed.returncode, 0, closed.stderr)
    self.assertEqual(json.loads(closed.stdout)["status"], "closed")
    self.assertTrue(worktree.is_dir())

  def test_claim_requires_stable_worker_identity(self):
    created = self.run_rwf("workspace", "create", "140")
    self.assertEqual(created.returncode, 0, created.stderr)
    self.env.pop("RWF_WORKER_ID")

    claimed = self.run_rwf("workspace", "claim", "RWF-140")

    self.assertEqual(claimed.returncode, 2)
    self.assertIn("RWF_WORKER_ID is required", claimed.stderr)

  def test_other_worker_cannot_release_claim(self):
    self.assertEqual(
      self.run_rwf("workspace", "create", "140").returncode,
      0,
    )
    self.assertEqual(
      self.run_rwf("workspace", "claim", "RWF-140").returncode,
      0,
    )
    self.env["RWF_WORKER_ID"] = "agent-b"

    released = self.run_rwf("workspace", "release", "RWF-140")

    self.assertEqual(released.returncode, 2)
    self.assertIn("owned by agent-a", released.stderr)

  def test_completion_and_help_share_workspace_grammar(self):
    created = self.run_rwf("workspace", "create", "140")
    self.assertEqual(created.returncode, 0, created.stderr)

    completed = self.run_rwf(
      "complete", "--", "workspace", "claim", ""
    )
    self.assertEqual(completed.returncode, 0, completed.stderr)
    self.assertEqual(completed.stdout.strip(), "RWF-140")

    helped = self.run_rwf("workspace", "--help")
    self.assertEqual(helped.returncode, 0, helped.stderr)
    for token in ("list", "create", "info", "claim", "release", "resume", "close"):
      self.assertIn(token, helped.stdout)


if __name__ == "__main__":
  unittest.main()
