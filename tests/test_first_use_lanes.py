from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"


class FirstUseLanesTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    subprocess.run(
      ["git", "init", "-b", "main"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"],
      cwd=root,
      check=True,
    )
    subprocess.run(
      ["git", "commit", "--allow-empty", "-m", "initial"],
      cwd=root,
      check=True,
      capture_output=True,
      text=True,
    )
    subprocess.run(
      [
        "git",
        "remote",
        "add",
        "origin",
        "https://github.com/Ma-XX-oN/RepoWorkflow.git",
      ],
      cwd=root,
      check=True,
    )

  def fake_github(self, base: Path) -> dict[str, str]:
    bin_dir = base / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
      "#!/usr/bin/env python3\n"
      "import json, sys\n"
      "args = sys.argv[1:]\n"
      "if args[:2] == ['issue', 'view'] and 'blockedBy' in args:\n"
      "  number = int(args[2])\n"
      "  deps = {206: [187, 189], 187: [], 189: []}[number]\n"
      "  print(json.dumps({'blockedBy': [{'number': n} for n in deps]}))\n"
      "elif args[:2] == ['issue', 'view']:\n"
      "  number = int(args[2])\n"
      "  titles = {206: 'Root', 187: 'Leaf A', 189: 'Leaf B'}\n"
      "  print(json.dumps({'number': number, 'title': titles[number], "
      "'state': 'OPEN', 'url': "
      "f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}'}))\n"
      "else:\n"
      "  print('unexpected gh arguments: ' + repr(args), file=sys.stderr)\n"
      "  raise SystemExit(2)\n",
      encoding="utf-8",
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env.pop("RWF_WRITER_ID", None)
    env.pop("RWF_SESSION_ID", None)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env

  def run_rwf(self, root: Path, env: dict[str, str], *words: str):
    return subprocess.run(
      [str(RWF), "--root", str(root), *words],
      cwd=root,
      env=env,
      capture_output=True,
      text=True,
    )

  def test_fresh_checkout_selects_and_renders_ticket_dependency_closure(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "206")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["206"])
      self.assertEqual(value["closure"], ["187", "189", "206"])
      self.assertEqual(
        value["assignment"],
        {"187": "A", "189": "B", "206": "A"},
      )

      graph = root / ".repoworkflow" / "state" / "relationships" / "graph.json"
      self.assertTrue(graph.is_file())
      graph_value = json.loads(graph.read_text(encoding="utf-8"))
      self.assertEqual(
        graph_value["value"]["issues"]["206"]["depends_on"],
        ["187", "189"],
      )

      common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
      ).stdout.strip()
      writer = (root / common / "repoworkflow" / "runtime-writer-id").resolve()
      self.assertTrue(writer.is_file())
      self.assertTrue(writer.read_text(encoding="utf-8").startswith("local-"))

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)
      self.assertEqual(
        listed.stdout.splitlines(),
        [
          " A.187  Leaf A",
          "*A.206  Root",
          "B.189  Leaf B",
        ],
      )

  def test_read_only_lane_failure_does_not_create_runtime_identity(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)

      listed = self.run_rwf(root, env, "lanes", "list")
      self.assertEqual(listed.returncode, 2)
      self.assertIn("lane selection is missing", listed.stderr)
      self.assertFalse(
        (root / ".git" / "repoworkflow" / "runtime-writer-id").exists()
      )

  def test_partial_explicit_identity_fails_without_synthesizing_other_half(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      env["RWF_WRITER_ID"] = "agent-explicit"

      selected = self.run_rwf(root, env, "lanes", "select", "206")
      self.assertEqual(selected.returncode, 2)
      self.assertIn("RWF_SESSION_ID", selected.stderr)
      self.assertFalse(
        (root / ".git" / "repoworkflow" / "runtime-writer-id").exists()
      )
      self.assertFalse((root / ".repoworkflow").exists())

  def test_explicit_agent_identity_is_preserved(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      env = self.fake_github(base)
      env["RWF_WRITER_ID"] = "agent-explicit"
      env["RWF_SESSION_ID"] = "session-explicit"

      selected = self.run_rwf(root, env, "lanes", "select", "206")
      self.assertEqual(selected.returncode, 0, selected.stderr)

      selection_path = (
        root
        / ".git"
        / "repoworkflow"
        / "lane-selection"
        / "selection.json"
      )
      record = json.loads(selection_path.read_text(encoding="utf-8"))
      self.assertEqual(record["writer_id"], "agent-explicit")
      self.assertEqual(record["session_id"], "session-explicit")

      writer_path = root / ".git" / "repoworkflow" / "runtime-writer-id"
      self.assertFalse(writer_path.exists())


if __name__ == "__main__":
  unittest.main()
