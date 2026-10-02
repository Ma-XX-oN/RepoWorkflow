from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .git import git
from .prelim import PRELIM_PREFIX, authoritative_main_sha, is_prelim_branch


class ServerPolicyError(RuntimeError):
  pass


@dataclass(frozen=True)
class IntegrationAdmission:
  source_branch: str
  base_branch: str
  candidate_sha: str
  validation_sha: str | None
  validation_passed: bool
  integration_authorized: bool


def check_integration_admission(root: Path, admission: IntegrationAdmission) -> None:
  root = root.resolve()
  config = load_config(root)
  integration_branch = config["repository"]["integrationBranch"]

  if not is_prelim_branch(admission.source_branch):
    raise ServerPolicyError(
      f"controlled integration source must be {PRELIM_PREFIX}<GUID>; "
      f"got {admission.source_branch}"
    )
  if admission.base_branch != integration_branch:
    raise ServerPolicyError(
      f"controlled integration target must be {integration_branch}; "
      f"got {admission.base_branch}"
    )

  candidate = git(
    root,
    "rev-parse",
    "--verify",
    f"{admission.candidate_sha}^{{commit}}",
    check=False,
  )
  if candidate.returncode or candidate.stdout.strip() != admission.candidate_sha:
    raise ServerPolicyError("integration candidate SHA is unavailable or invalid")

  current_main = authoritative_main_sha(root, config)
  current = git(
    root,
    "merge-base",
    "--is-ancestor",
    current_main,
    admission.candidate_sha,
    check=False,
  )
  if current.returncode:
    raise ServerPolicyError(
      "integration candidate is stale: authoritative main is not an ancestor"
    )

  if admission.validation_sha != admission.candidate_sha:
    raise ServerPolicyError("required validation does not apply to exact candidate SHA")
  if not admission.validation_passed:
    raise ServerPolicyError("required validation is missing or failed")
  if not admission.integration_authorized:
    raise ServerPolicyError("explicit integration authorization is absent")


def required_github_rules() -> dict:
  """Describe the remote controls needed around the admission check."""
  return {
    "main": {
      "requirePullRequest": True,
      "blockDirectPush": True,
      "blockForcePush": True,
      "blockDeletion": True,
      "requireStatusCheck": "RepoWorkflow integration admission",
      "requireCurrentBase": True,
      "bypass": "no ordinary development actor",
    },
    "stableTags": {
      "pattern": "v[0-9]+.[0-9]+.[0-9]+",
      "blockUpdate": True,
      "blockDeletion": True,
      "creation": "controlled finalizer only",
    },
  }
