from __future__ import annotations

import csv
import json
from pathlib import Path
import re
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
    dependencies = {}
    with CANONICAL_TICKETS.open(
      newline="",
      encoding="utf-8",
    ) as handle:
      for row in csv.DictReader(handle):
        issue = row["issue"]
        issues[issue] = row["title"]
        dependencies[issue] = [
          int(value)
          for value in row["dependencies"].split(";")
          if value
        ]

    dependants = {issue: [] for issue in issues}
    for issue, values in dependencies.items():
      for dependency in values:
        dependants[str(dependency)].append(int(issue))
    graph_data = {
      "issues": issues,
      "dependencies": dependencies,
      "dependants": {
        issue: sorted(values)
        for issue, values in dependants.items()
      },
    }
    data = root / "issues.json"
    data.write_text(
      json.dumps(graph_data, sort_keys=True) + "\n",
      encoding="utf-8",
    )
    script = root / "scripts" / "canonical_info.py"
    script.write_text(
      "import json, pathlib, sys\n"
      "data = json.loads((pathlib.Path(__file__).parents[1] / "
      "'issues.json').read_text(encoding='utf-8'))\n"
      "issues = data['issues']\n"
      "args = sys.argv[1:]\n"
      "if args == ['issue', 'list-open']:\n"
      "  values = [\n"
      "    {'number': int(number), 'title': title}\n"
      "    for number, title in sorted(issues.items(), key=lambda item: int(item[0]))\n"
      "  ]\n"
      "  print(json.dumps({'schema_version': 1, 'issues': values}))\n"
      "elif args[:2] == ['dependency', 'related']:\n"
      "  number = str(int(args[2]))\n"
      "  print(json.dumps({\n"
      "    'schema_version': 1,\n"
      "    'issue': int(number),\n"
      "    'dependencies': data['dependencies'][number],\n"
      "    'dependants': data['dependants'][number],\n"
      "  }))\n"
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
    config["dependencyCommand"] = [sys.executable, str(script)]
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

  def test_focus_seed_413_preserves_canonical_component(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      self.make_repo(root)

      with CANONICAL_TICKETS.open(
        newline="",
        encoding="utf-8",
      ) as handle:
        rows = {
          row["issue"]: row
          for row in csv.DictReader(handle)
          if row["issue"] in {"409", "410", "411", "412", "413"}
        }
      self.assertEqual(
        {
          issue: row["dependencies"]
          for issue, row in rows.items()
        },
        {
          "409": "413",
          "410": "",
          "411": "410",
          "412": "410;456",
          "413": "410;411;412",
        },
      )
      self.assertTrue(rows["409"]["title"].startswith("Epic:"))

      selected = self.run_rwf(
        root,
        "lanes",
        "select",
        "413",
        "--json",
      )
      self.assertEqual(selected.returncode, 0, selected.stderr)
      value = json.loads(selected.stdout)
      self.assertEqual(value["roots"], ["413"])
      self.assertEqual(
        value["closure"],
        ["409", "410", "411", "412", "413", "456"],
      )

      rendered = self.run_rwf(root, "lanes", "select", "413")
      self.assertEqual(rendered.returncode, 0, rendered.stderr)
      self.assertEqual(rendered.stdout.count("*"), 1)
      self.assertRegex(rendered.stdout, re.compile(r"\*[A-Z]+413\b"))
      for issue in ("409", "410", "411", "412", "413", "456"):
        self.assertIn(issue, rendered.stdout)

      repeated = self.run_rwf(root, "lanes", "select", "413")
      self.assertEqual(repeated.returncode, 0, repeated.stderr)
      self.assertEqual(repeated.stdout, rendered.stdout)

      restarted = self.run_rwf(root, "lanes", "view")
      self.assertEqual(restarted.returncode, 0, restarted.stderr)
      self.assertEqual(restarted.stdout, rendered.stdout)

      debug = self.run_rwf(root, "lanes", "view", "--debug")
      self.assertEqual(debug.returncode, 0, debug.stderr)
      for edge in (
        "410 -> 411",
        "410 -> 412",
        "410 -> 413",
        "411 -> 413",
        "412 -> 413",
        "413 -> 409",
      ):
        self.assertIn(edge, debug.stdout)

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
