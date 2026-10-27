from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]
RWF = ROOT / "rwf"
PYTHON_ENTRY = ROOT / "repo_workflow.py"
CANONICAL_TICKETS = ROOT / ".repoworkflow" / "tickets.csv"
TYPE_PREFIXES = ("Initiative:", "Epic:", "Feature:")


def capture_utf8(command, *, cwd):
  result = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
  return subprocess.CompletedProcess(
    result.args,
    result.returncode,
    result.stdout.decode("utf-8", "strict"),
    result.stderr.decode("utf-8", "strict"),
  )


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
    # A POSIX shell launcher is not directly executable by Win32.
    # The existing Python CLI is the same application on every platform.
    executable = (
      [sys.executable, str(PYTHON_ENTRY)]
      if sys.platform == "win32"
      else [str(RWF)]
    )
    return capture_utf8(
      [*executable, "--root", str(root), *args],
      cwd=root,
    )

  def test_invalid_utf8_cli_output_is_not_silently_replaced(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      stub = root / "stub_cli.py"
      stub.write_text(
        "import os\n"
        "os.write(1, bytes([255]))\n",
        encoding="utf-8",
      )
      if sys.platform == "win32":
        with patch(f"{__name__}.PYTHON_ENTRY", stub):
          with self.assertRaises(UnicodeDecodeError):
            self.run_rwf(root, "issue", "list")
      else:
        launcher = root / "run-stub"
        launcher.write_text(
          "#!/bin/sh\n"
          f"exec {shlex.quote(sys.executable)} "
          f"{shlex.quote(str(stub))} \"$@\"\n",
          encoding="utf-8",
        )
        launcher.chmod(0o755)
        with patch(f"{__name__}.RWF", launcher):
          with self.assertRaises(UnicodeDecodeError):
            self.run_rwf(root, "issue", "list")

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
