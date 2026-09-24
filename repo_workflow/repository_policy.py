from __future__ import annotations

from pathlib import Path

from .actions_policy import check_actions_policy
from .branch_policy import _load_policy
from .config import load_config
from .git import git
from .github_adapter import load_github_config


CANONICAL_REPOWORKFLOW_URL = "https://github.com/Ma-XX-oN/RepoWorkflow.git"


class RepositoryPolicyError(RuntimeError):
  pass


def check_submodule(root: Path, engine_root: Path) -> None:
  try:
    relative = engine_root.resolve().relative_to(root.resolve()).as_posix()
  except ValueError as exc:
    raise RepositoryPolicyError("RepoWorkflow must be inside the consumer repository") from exc
  if relative != "RepoWorkflow":
    raise RepositoryPolicyError(
      f"RepoWorkflow must be mounted at RepoWorkflow, not {relative}"
    )
  entry = git(root, "ls-files", "--stage", "--", "RepoWorkflow", check=False)
  if entry.returncode or not entry.stdout.strip():
    raise RepositoryPolicyError("RepoWorkflow is not tracked as a submodule")
  mode = entry.stdout.split()[0]
  if mode != "160000":
    raise RepositoryPolicyError("RepoWorkflow must be a Git submodule (mode 160000)")
  expected = git(root, "rev-parse", "HEAD:RepoWorkflow").stdout.strip()
  actual = git(engine_root, "rev-parse", "HEAD", check=False)
  if actual.returncode or actual.stdout.strip() != expected:
    raise RepositoryPolicyError(
      "RepoWorkflow checkout does not match the superproject's pinned gitlink"
    )
  path = git(
    root,
    "config",
    "-f",
    ".gitmodules",
    "--get",
    "submodule.RepoWorkflow.path",
    check=False,
  )
  url = git(
    root,
    "config",
    "-f",
    ".gitmodules",
    "--get",
    "submodule.RepoWorkflow.url",
    check=False,
  )
  if path.returncode or path.stdout.strip() != "RepoWorkflow":
    raise RepositoryPolicyError(".gitmodules must declare RepoWorkflow path")
  if url.returncode or not url.stdout.strip():
    raise RepositoryPolicyError(".gitmodules must declare RepoWorkflow URL")
  if url.stdout.strip() != CANONICAL_REPOWORKFLOW_URL:
    raise RepositoryPolicyError(
      "RepoWorkflow submodule must use the canonical repository URL: "
      + CANONICAL_REPOWORKFLOW_URL
    )


def check_repository_policy(root: Path, engine_root: Path) -> None:
  check_submodule(root, engine_root)
  config = load_config(root)
  github = load_github_config(root)
  branch_policy = _load_policy(root)
  if not (root / ".ci" / "run-ci-request").is_file():
    raise RepositoryPolicyError(".ci/run-ci-request is required")
  if branch_policy["integrationBranch"] != config["repository"]["integrationBranch"]:
    raise RepositoryPolicyError(
      "branch-policy integrationBranch must match repoworkflow repository integrationBranch"
    )
  env_ids = {env["id"] for env in config["environments"]}
  if set(github["runners"]) != env_ids:
    raise RepositoryPolicyError(
      "github.json runners must map exactly the declared validation environments"
    )
  check_actions_policy(
    root,
    engine_root,
    migration_workflows=github.get("migrationWorkflows", []),
  )
