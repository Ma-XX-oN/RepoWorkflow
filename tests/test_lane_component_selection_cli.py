from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"


class LaneComponentSelectionCliTests(unittest.TestCase):
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

  def write_ticket_state(self, root: Path) -> None:
    rows = (
      (435, "Epic: Model dependent lanes and execution-aware lane ordering",
       "439"),
      (436, "Specify dependent-lane decomposition, execution order, and "
       "readiness semantics", ""),
      (437, "Implement automatic dependent-lane decomposition for shared "
       "prerequisites and convergence", "436"),
      (438, "List lanes and issues in execution order with dependency "
       "readiness status", "436"),
      (439, "Certify dependent-lane decomposition, ordering, and readiness "
       "transitions", "437;438"),
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("issue", "title", "dependencies"))
    writer.writerows(rows)
    path = root / ".repoworkflow" / "tickets.csv"
    path.parent.mkdir(parents=True)
    path.write_text(output.getvalue(), encoding="utf-8")

  def fake_github(self, base: Path) -> dict[str, str]:
    calls = base / "gh-calls.jsonl"
    calls.write_text("", encoding="utf-8")
    bin_dir = base / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
      "#!/usr/bin/env python3\n"
      "import json, os, sys\n"
      "args = sys.argv[1:]\n"
      "with open(os.environ['RWF_TEST_CALLS'], 'a', encoding='utf-8') as log:\n"
      "  log.write(json.dumps(args) + '\\n')\n"
      "if args[:2] == ['issue', 'view'] and any('blockedBy' in arg for arg in args):\n"
      "  print('dependency provider must not be used', file=sys.stderr)\n"
      "  raise SystemExit(96)\n"
      "if args[:2] == ['issue', 'view']:\n"
      "  number = int(args[2])\n"
      "  titles = {\n"
      "    435: 'Epic: Model dependent lanes and execution-aware lane ordering',\n"
      "    436: 'Specify dependent-lane decomposition, execution order, and readiness semantics',\n"
      "    437: 'Implement automatic dependent-lane decomposition for shared prerequisites and convergence',\n"
      "    438: 'List lanes and issues in execution order with dependency readiness status',\n"
      "    439: 'Certify dependent-lane decomposition, ordering, and readiness transitions',\n"
      "  }\n"
      "  print(json.dumps({\n"
      "    'number': number, 'title': titles[number], 'state': 'OPEN',\n"
      "    'url': f'https://github.com/Ma-XX-oN/RepoWorkflow/issues/{number}',\n"
      "  }))\n"
      "  raise SystemExit(0)\n"
      "print('unexpected gh arguments: ' + repr(args), file=sys.stderr)\n"
      "raise SystemExit(97)\n",
      encoding="utf-8",
    )
    gh.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["RWF_TEST_CALLS"] = str(calls)
    return env

  def run_rwf(self, root: Path, env: dict[str, str], *words: str):
    return subprocess.run(
      [str(RWF), "--root", str(root), *words],
      cwd=root,
      env=env,
      capture_output=True,
      text=True,
    )

  def dependency_calls(self, env: dict[str, str]) -> list[list[str]]:
    path = Path(env["RWF_TEST_CALLS"])
    return [
      json.loads(line)
      for line in path.read_text(encoding="utf-8").splitlines()
      if "blockedBy" in line
    ]

  def test_focus_seed_renders_complete_synchronized_component(self):
    with tempfile.TemporaryDirectory() as td:
      base = Path(td)
      root = base / "repo"
      root.mkdir()
      self.make_repo(root)
      self.write_ticket_state(root)
      env = self.fake_github(base)

      selected = self.run_rwf(root, env, "lanes", "select", "436")
      self.assertEqual(selected.returncode, 0, selected.stderr)
      for issue in range(435, 440):
        self.assertIn(str(issue), selected.stdout)
      self.assertIn("*?A436", selected.stdout)
      self.assertEqual(selected.stdout.count("*"), 1)
      self.assertEqual(self.dependency_calls(env), [])

      gh = Path(env["PATH"].split(os.pathsep)[0]) / "gh"
      gh.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('provider unavailable', file=sys.stderr)\n"
        "raise SystemExit(93)\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)

      root_selected = self.run_rwf(
        root,
        env,
        "lanes",
        "select",
        "435",
        "--json",
      )
      self.assertEqual(root_selected.returncode, 0, root_selected.stderr)
      value = json.loads(root_selected.stdout)
      self.assertEqual(value["roots"], ["435"])
      self.assertEqual(value["closure"], ["435", "436", "437", "438", "439"])
      self.assertNotIn("provider unavailable", root_selected.stderr)


if __name__ == "__main__":
  unittest.main()
