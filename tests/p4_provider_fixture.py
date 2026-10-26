"""P4 explicit cross-process repo-info and dependency test adapters."""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "repo_workflow.py"
FIXTURE = Path(__file__).resolve()
REPO = "Ma-XX-oN/RepoWorkflow"


def _read(path):
  return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, data):
  Path(path).write_text(json.dumps(data), encoding="utf-8")


def configure_provider(base: Path, dependencies, titles=None):
  defaults = {
    206: "Root 206", 203: "Root 203", 201: "Leaf 201",
    205: "Root 205", 208: "Leaf 208", 218: "Root 218",
    217: "Leaf 217", 187: "Leaf A", 189: "Leaf B",
  }
  defaults.update(titles or {})
  numbers = sorted({n for issue, deps in dependencies.items()
                    for n in (issue, *deps)})
  _write(base / "metadata.json", {
    str(n): {"title": defaults.get(n, f"Issue {n}"), "state": "OPEN"}
    for n in numbers
  })
  _write(base / "dependencies.json", {
    str(issue): deps for issue, deps in dependencies.items()
  })
  _write(base / "provider-mode.json", {})
  (base / "provider-calls.jsonl").write_text("", encoding="utf-8")
  (base / "dependency-calls.jsonl").write_text("", encoding="utf-8")
  config = {
    "schema": 1,
    "versionCommand": [sys.executable, "-c", "print('1.0.0')"],
    "repository": {
      "integrationBranch": "main", "authoritativeRemote": "origin",
    },
    "environments": [{
      "id": "fixture", "platform": "any",
      "validationCommand": [sys.executable, "-c", "print('ok')"],
    }],
    "infoCommand": [sys.executable, str(FIXTURE), "info", str(base)],
    "dependencyCommand": [sys.executable, str(FIXTURE), "dependency", str(base)],
  }
  target = base / "repo" / ".ci" / "repoworkflow.json"
  target.parent.mkdir(parents=True, exist_ok=True)
  _write(target, config)
  env = dict(os.environ)
  for key in ("GH_TOKEN", "GITHUB_TOKEN", "RWF_WRITER_ID", "RWF_SESSION_ID"):
    env.pop(key, None)
  env.update({
    "RWF_TEST_META": str(base / "metadata.json"),
    "RWF_TEST_DEPS": str(base / "dependencies.json"),
    "RWF_TEST_CALLS": str(base / "dependency-calls.jsonl"),
    "RWF_TEST_PROVIDER_LOG": str(base / "provider-calls.jsonl"),
    "RWF_TEST_FIXTURE_BASE": str(base),
  })
  return env


def verify_provider(root, env):
  base = env["RWF_TEST_FIXTURE_BASE"]
  config = _read(root / ".ci" / "repoworkflow.json")
  for field, mode in (("infoCommand", "info"),
                      ("dependencyCommand", "dependency")):
    assert config[field] == [sys.executable, str(FIXTURE), mode, base], field
  assert "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
  assert not (Path(base) / "bin").exists()


def provider_calls(env):
  return [
    json.loads(row) for row in
    Path(env["RWF_TEST_PROVIDER_LOG"]).read_text(
      encoding="utf-8",
    ).splitlines() if row
  ]


def set_provider_failure(env, info=None, dependency=None):
  _write(Path(env["RWF_TEST_FIXTURE_BASE"]) / "provider-mode.json", {
    "info": info, "dependency": dependency,
  })


def set_metadata_titles(env, titles):
  path = Path(env["RWF_TEST_META"])
  metadata = _read(path)
  for number, title in titles.items():
    metadata[str(number)]["title"] = title
  _write(path, metadata)


def _number(word):
  if not word.isdecimal() or int(word) <= 0:
    raise ValueError("invalid issue number")
  return int(word)


def _route(kind, base, args):
  with (base / "provider-calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"kind": kind, "args": args}) + "\n")
  message = _read(base / "provider-mode.json").get(kind)
  if message:
    raise ValueError(message)
  if kind == "info":
    metadata = _read(base / "metadata.json")
    if args == ["repository"]:
      return {"schema_version": 1, "repository": REPO, "provider": "github"}
    if args == ["issue", "list-open"]:
      return {
        "schema_version": 1,
        "issues": [
          {"number": int(n), "title": item["title"]}
          for n, item in sorted(metadata.items(), key=lambda pair: int(pair[0]))
          if item["state"] == "OPEN"
        ],
      }
    if len(args) == 3 and args[:2] == ["issue", "get"]:
      number = _number(args[2])
      item = metadata[str(number)]
      if "/pull/" in item.get("url", ""):
        raise ValueError(f"#{number} is a pull request, not an issue")
      return {
        "schema_version": 1, "number": number,
        "title": item["title"], "state": item["state"].lower(),
        "link": item.get("url", f"https://github.com/{REPO}/issues/{number}"),
      }
  if kind == "dependency" and len(args) >= 3 and args[0] == "dependency":
    state = _read(base / "dependencies.json")
    number = _number(args[2])
    current = state[str(number)]
    if len(args) == 3 and args[:2] in (
      ["dependency", "related"], ["dependency", "get"],
    ):
      with (base / "dependency-calls.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"kind": "dependency", "issue": number}) + "\n")
    if args[:2] == ["dependency", "related"] and len(args) == 3:
      blocking = sorted(int(n) for n, deps in state.items() if number in deps)
      return {
        "schema_version": 1, "issue": number,
        "dependencies": current, "dependants": blocking,
      }
    if args[:2] == ["dependency", "get"] and len(args) == 3:
      return {"schema_version": 1, "issue": number, "dependencies": current}
  raise ValueError(f"unexpected provider arguments: {kind} {args!r}")


def main(argv):
  if len(argv) < 2 or argv[0] not in {"info", "dependency"}:
    print("unexpected provider arguments", file=sys.stderr)
    return 2
  mode, base, *args = argv
  try:
    print(json.dumps(_route(mode, Path(base), args)))
  except (ValueError, KeyError, OSError, TypeError) as error:
    print(str(error), file=sys.stderr)
    return 2
  return 0


class FirstUseFixture:
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

  def fake_github(
    self, base: Path, dependencies: dict[int, list[int]] | None = None,
    titles: dict[int, str] | None = None,
  ) -> dict[str, str]:
    return configure_provider(base, dependencies if dependencies is not None else {
      206: [], 203: [201], 201: [], 205: [208], 208: [],
      218: [217], 217: [], 187: [], 189: [],
    }, titles)

  def ticket_rows(self, root: Path) -> dict[str, dict[str, str]]:
    path = root / ".repoworkflow" / "tickets.csv"
    with path.open(newline="", encoding="utf-8") as handle:
      return {
        row["issue"]: row
        for row in csv.DictReader(handle)
      }

  def dependency_calls(self, env: dict[str, str]) -> list[int]:
    path = Path(env["RWF_TEST_CALLS"])
    return [
      json.loads(line)["issue"]
      for line in path.read_text(encoding="utf-8").splitlines()
      if line
    ]

  def certify_migration(self, root: Path) -> None:
    source = (
      ROOT
      / ".repoworkflow"
      / "migrations"
      / "native-dependencies-v1.json"
    )
    target = (
      root
      / ".repoworkflow"
      / "migrations"
      / "native-dependencies-v1.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    certification = {
      "schema_version": 1,
      "migration_id": "repoworkflow-native-dependencies-v1",
      "repository": "Ma-XX-oN/RepoWorkflow",
      "manifest_sha256": digest,
      "provider_readback_sha256": "0" * 64,
    }
    target.with_name("native-dependencies-v1.certified.json").write_text(
      json.dumps(certification),
      encoding="utf-8",
    )

  def run_rwf(self, root: Path, env: dict[str, str], *words: str):
    verify_provider(root, env)
    return subprocess.run(
      [sys.executable, str(CLI), "--root", str(root), *words],
      cwd=root,
      env=env,
      capture_output=True,
      text=True, encoding="utf-8", errors="strict",
    )



if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
