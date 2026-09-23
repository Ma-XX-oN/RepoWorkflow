import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repo_workflow.repository_policy import (
  RepositoryPolicyError,
  check_repository_policy,
)


class RepositoryPolicyTests(unittest.TestCase):
  def git(self, root, *args):
    return subprocess.run(
      ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )

  def make_consumer(self):
    td = tempfile.TemporaryDirectory()
    base = Path(td.name)
    engine_source = base / "engine-source"
    engine_remote = base / "engine.git"
    consumer = base / "consumer"
    engine_source.mkdir()
    consumer.mkdir()

    self.git(engine_source, "init", "-b", "main")
    self.git(engine_source, "config", "user.name", "Test")
    self.git(engine_source, "config", "user.email", "test@example.invalid")
    (engine_source / "templates" / "github").mkdir(parents=True)
    canonical = "name: CI\n"
    (engine_source / "templates" / "github" / "ci.yml").write_text(canonical)
    self.git(engine_source, "add", ".")
    self.git(engine_source, "commit", "-m", "engine")
    subprocess.run(["git", "init", "--bare", str(engine_remote)], check=True,
                   capture_output=True)
    self.git(engine_source, "remote", "add", "origin", str(engine_remote))
    self.git(engine_source, "push", "-u", "origin", "main")
    subprocess.run(
      ["git", "--git-dir", str(engine_remote), "symbolic-ref", "HEAD", "refs/heads/main"],
      check=True, capture_output=True,
    )

    self.git(consumer, "init", "-b", "main")
    self.git(consumer, "config", "user.name", "Test")
    self.git(consumer, "config", "user.email", "test@example.invalid")
    subprocess.run(
      ["git", "-c", "protocol.file.allow=always", "submodule", "add",
       str(engine_remote), "RepoWorkflow"],
      cwd=consumer, check=True, capture_output=True,
    )
    self.git(
      consumer, "config", "-f", ".gitmodules",
      "submodule.RepoWorkflow.url",
      "https://github.com/Ma-XX-oN/RepoWorkflow.git",
    )
    (consumer / ".github" / "workflows").mkdir(parents=True)
    (consumer / ".github" / "workflows" / "ci.yml").write_text(canonical)
    (consumer / ".ci").mkdir()
    (consumer / ".ci" / "run-ci-request").write_text("1.0.0-issue.1.1\n")
    (consumer / ".ci" / "branch-policy.json").write_text(json.dumps({
      "schema": 1, "integrationBranch": "main", "branches": {}, "patterns": []
    }))
    (consumer / ".ci" / "github.json").write_text(json.dumps({
      "schema": 1, "prepareRunner": "ubuntu-latest", "runners": {"local": "ubuntu-latest"}
    }))
    (consumer / ".ci" / "repoworkflow.json").write_text(json.dumps({
      "schema": 1,
      "versionCommand": [sys.executable, "scripts/version.py"],
      "repository": {"integrationBranch": "main", "authoritativeRemote": "origin"},
      "environments": [{
        "id": "local", "required": True, "platform": "any",
        "validationCommand": [sys.executable, "scripts/validate.py"],
      }],
      "artifacts": [],
    }))
    self.git(consumer, "add", ".")
    self.git(consumer, "commit", "-m", "consumer")
    return td, consumer

  def test_pinned_submodule_and_canonical_adapter_pass(self):
    td, consumer = self.make_consumer()
    with td:
      check_repository_policy(consumer, consumer / "RepoWorkflow")

  def test_copied_engine_directory_is_not_a_submodule(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      engine = root / "RepoWorkflow"
      engine.mkdir()
      with self.assertRaises(RepositoryPolicyError):
        check_repository_policy(root, engine)

  def test_noncanonical_submodule_source_is_rejected(self):
    td, consumer = self.make_consumer()
    with td:
      self.git(
        consumer, "config", "-f", ".gitmodules",
        "submodule.RepoWorkflow.url", "https://example.invalid/RepoWorkflow.git",
      )
      with self.assertRaisesRegex(RepositoryPolicyError, "canonical repository"):
        check_repository_policy(consumer, consumer / "RepoWorkflow")

  def test_mismatched_integration_branch_is_rejected(self):
    td, consumer = self.make_consumer()
    with td:
      path = consumer / ".ci" / "branch-policy.json"
      value = json.loads(path.read_text())
      value["integrationBranch"] = "master"
      path.write_text(json.dumps(value))
      with self.assertRaisesRegex(RepositoryPolicyError, "integrationBranch"):
        check_repository_policy(consumer, consumer / "RepoWorkflow")


if __name__ == "__main__":
  unittest.main()
