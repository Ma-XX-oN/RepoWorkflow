from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "github-ticket-dependencies.py"


class GitHubTicketDependencyAdapterTests(unittest.TestCase):
  def fake_gh(self, root: Path) -> tuple[dict, Path]:
    state = root / "state.json"
    state.write_text(json.dumps({"blockedBy": [2, 9]}), encoding="utf-8")
    log = root / "log.jsonl"
    gh = root / ("gh.cmd" if os.name == "nt" else "gh")
    if os.name == "nt":
      gh.write_text(
        f'@echo off\r\n"{sys.executable}" "{root / "fake_gh.py"}" %*\r\n',
        encoding="utf-8",
      )
    else:
      gh.write_text(
        f"#!{sys.executable}\n"
        f"exec(open({str(root / 'fake_gh.py')!r}).read())\n",
        encoding="utf-8",
      )
      gh.chmod(0o755)
    (root / "fake_gh.py").write_text(
      "import json, sys\n"
      f"state_path = {str(state)!r}\n"
      f"log_path = {str(log)!r}\n"
      "args = sys.argv[1:]\n"
      "with open(log_path, 'a', encoding='utf-8') as f:\n"
      "  f.write(json.dumps(args) + '\\n')\n"
      "state = json.load(open(state_path, encoding='utf-8'))\n"
      "if args[:2] == ['issue', 'view']:\n"
      "  print(json.dumps({'blockedBy': [{'number': n} for n in state['blockedBy']]}))\n"
      "elif args[:2] == ['issue', 'edit']:\n"
      "  if '--remove-blocked-by' in args:\n"
      "    raw = args[args.index('--remove-blocked-by') + 1]\n"
      "    remove = {int(x) for x in raw.split(',') if x}\n"
      "    state['blockedBy'] = [n for n in state['blockedBy'] if n not in remove]\n"
      "  if '--add-blocked-by' in args:\n"
      "    raw = args[args.index('--add-blocked-by') + 1]\n"
      "    state['blockedBy'] = sorted(set(state['blockedBy']) | {int(x) for x in raw.split(',') if x})\n"
      "  json.dump(state, open(state_path, 'w', encoding='utf-8'))\n"
      "else:\n"
      "  raise SystemExit(9)\n",
      encoding="utf-8",
    )
    return {"PATH": str(root) + os.pathsep + os.environ.get("PATH", "")}, log

  def run_adapter(self, env: dict, *args: str):
    merged = dict(os.environ)
    merged.update(env)
    return subprocess.run(
      [sys.executable, str(ADAPTER), *args],
      capture_output=True,
      text=True,
      env=merged,
    )

  def test_read_normalizes_blocked_by_numbers(self):
    with tempfile.TemporaryDirectory() as td:
      env, _ = self.fake_gh(Path(td))
      result = self.run_adapter(env, "dependency", "get", "64")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(json.loads(result.stdout), {
        "schema_version": 1, "issue": 64, "dependencies": [2, 9]
      })

  def test_replace_removes_adds_and_confirms_exact_set(self):
    with tempfile.TemporaryDirectory() as td:
      env, log = self.fake_gh(Path(td))
      result = self.run_adapter(env, "dependency", "replace", "64", "9", "54")
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(json.loads(result.stdout)["dependencies"], [9, 54])
      calls = [json.loads(line) for line in log.read_text().splitlines()]
      self.assertIn(
        ["issue", "edit", "64", "--remove-blocked-by", "2"],
        calls,
      )
      self.assertIn(
        ["issue", "edit", "64", "--add-blocked-by", "54"],
        calls,
      )
      self.assertEqual(
        sum(call[:2] == ["issue", "view"] for call in calls),
        2,
      )

  def test_identical_replace_is_idempotent_read_only(self):
    with tempfile.TemporaryDirectory() as td:
      env, log = self.fake_gh(Path(td))
      result = self.run_adapter(env, "dependency", "replace", "64", "9", "2")
      self.assertEqual(result.returncode, 0, result.stderr)
      calls = [json.loads(line) for line in log.read_text().splitlines()]
      self.assertFalse(any(call[:2] == ["issue", "edit"] for call in calls))

  def test_provider_failure_is_nonzero(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      gh = root / ("gh.cmd" if os.name == "nt" else "gh")
      if os.name == "nt":
        gh.write_text("@echo off\r\nexit /b 7\r\n", encoding="utf-8")
      else:
        gh.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        gh.chmod(0o755)
      result = self.run_adapter(
        {"PATH": str(root) + os.pathsep + os.environ.get("PATH", "")},
        "dependency", "get", "64",
      )
      self.assertNotEqual(result.returncode, 0)
      self.assertIn("GitHub dependency operation failed", result.stderr)


if __name__ == "__main__":
  unittest.main()
