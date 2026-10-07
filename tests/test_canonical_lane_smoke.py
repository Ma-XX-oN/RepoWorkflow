from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"
CANONICAL_TICKETS = ROOT / ".repoworkflow" / "tickets.csv"
TYPE_PREFIXES = ("Initiative:", "Epic:", "Feature:")


class CanonicalLaneSmokeTests(unittest.TestCase):
  def make_repo(self, root: Path) -> None:
    RepoFixture(root)
    target = root / ".repoworkflow" / "tickets.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CANONICAL_TICKETS, target)

    issues = {}
    with CANONICAL_TICKETS.open(
      newline="",
      encoding="utf-8",
    ) as handle:
      for row in csv.DictReader(handle):
        issues[row["issue"]] = row["title"]

    data = root / "issues.json"
    data.write_text(
      json.dumps(issues, sort_keys=True) + "\n",
      encoding="utf-8",
    )
    script = root / "scripts" / "canonical_info.py"
    script.write_text(
      "import json, pathlib, sys\n"
      "issues = json.loads((pathlib.Path(__file__).parents[1] / "
      "'issues.json').read_text(encoding='utf-8'))\n"
      "args = sys.argv[1:]\n"
      "if args == ['issue', 'list-open']:\n"
      "  values = [\n"
      "    {'number': int(number), 'title': title}\n"
      "    for number, title in sorted(issues.items(), key=lambda item: int(item[0]))\n"
      "  ]\n"
      "  print(json.dumps({'schema_version': 1, 'issues': values}))\n"
      "else:\n"
      "  number = str(int(args[-1]))\n"
      "  print(json.dumps({\n"
      "    'schema_version': 1,\n"
      "    'number': int(number),\n"
      "    'title': issues[number],\n"
      "    'state': 'open',\n"
      "    'link': f'https://example.invalid/issues/{number}',\n"
      "  }))\n",
      encoding="utf-8",
    )
    config_path = root / ".ci" / "repoworkflow.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["infoCommand"] = [sys.executable, str(script)]
    config_path.write_text(
      json.dumps(config, indent=2) + "\n",
      encoding="utf-8",
    )

  def run_rwf(self, root: Path, *args: str):
    return subprocess.run(
      [str(RWF), "--root", str(root), *args],
      cwd=root,
      capture_output=True,
      text=True,
    )

  def test_current_typed_issue_smoke_renders_through_public_cli(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      listed = self.run_rwf(root, "issue", "list")
      self.assertEqual(listed.returncode, 0, listed.stderr)

      selected = []
      for line in listed.stdout.splitlines():
        if not line.startswith("#"):
          continue
        number, _, title = line[1:].partition("  ")
        if title.startswith(TYPE_PREFIXES):
          selected.append(number)
      self.assertTrue(selected)

      rendered = self.run_rwf(
        root,
        "lanes",
        "select",
        *selected,
      )
      self.assertEqual(rendered.returncode, 0, rendered.stderr)
      self.assertTrue(rendered.stdout.strip())


if __name__ == "__main__":
  unittest.main()
