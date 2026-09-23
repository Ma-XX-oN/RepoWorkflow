from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


class RepoFixture:
  def __init__(
    self,
    root: Path,
    *,
    version: str = "1.0.0-issue.1.1",
    validation_body: str = "raise SystemExit(0)\n",
    platform: str = "any",
    artifacts: list[dict] | None = None,
  ):
    self.root = root
    self.remote = root.parent / f"{root.name}-remote.git"
    self.version = version
    self._run("init", "-b", "issue-1-test")
    self._run("config", "user.name", "Test")
    self._run("config", "user.email", "test@example.invalid")
    subprocess.run(["git", "init", "--bare", str(self.remote)], check=True,
                   capture_output=True)
    self._run("remote", "add", "origin", str(self.remote))
    (root / ".ci").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "scripts" / "version.py").write_text(
      "from pathlib import Path\n"
      "print((Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip())\n",
      encoding="utf-8",
    )
    (root / "scripts" / "validate.py").write_text(validation_body, encoding="utf-8")
    config = {
      "schema": 1,
      "versionCommand": [sys.executable, "scripts/version.py"],
      "repository": {
        "integrationBranch": "main",
        "authoritativeRemote": "origin",
      },
      "environments": [{
        "id": "local",
        "required": True,
        "platform": platform,
        "capabilities": [],
        "validationCommand": [sys.executable, "scripts/validate.py"],
      }],
      "artifacts": artifacts or [],
    }
    (root / ".ci" / "repoworkflow.json").write_text(
      json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (root / ".ci" / "run-ci-request").write_text(version + "\n", encoding="utf-8")
    (root / ".ci" / "branch-policy.json").write_text(json.dumps({
      "schema": 1,
      "integrationBranch": "main",
      "branches": {
        "issue-1-test": {"parent": "main", "allowedDependencies": []}
      },
      "patterns": [],
    }, indent=2) + "\n", encoding="utf-8")
    (root / ".ci" / "github.json").write_text(json.dumps({
      "schema": 1,
      "prepareRunner": "ubuntu-latest",
      "runners": {"local": "ubuntu-latest"},
    }, indent=2) + "\n", encoding="utf-8")
    self.commit("candidate")
    self._run("branch", "main")
    self._run("push", "-u", "origin", "issue-1-test")
    self._run("push", "origin", "main")

  def _run(self, *args: str, check: bool = True):
    return subprocess.run(
      ["git", *args], cwd=self.root, check=check, text=True,
      capture_output=True,
    )

  def commit(self, message: str) -> str:
    self._run("add", ".")
    self._run("commit", "-m", message)
    return self.head()

  def head(self) -> str:
    return self._run("rev-parse", "HEAD").stdout.strip()

  def push(self) -> None:
    self._run("push", "origin", "HEAD:issue-1-test")

  def tag_remote(self, tag: str) -> None:
    self._run("tag", tag)
    self._run("push", "origin", f"refs/tags/{tag}")
    self._run("tag", "-d", tag)
