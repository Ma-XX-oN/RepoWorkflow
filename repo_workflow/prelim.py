from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import changed_files, current_branch, git, head_sha
from .version_adapter import read_stable_version


PRELIM_BRANCH = "prelim-main"


class PrelimError(RuntimeError):
  pass


@dataclass(frozen=True)
class PrelimStatus:
  present: bool
  candidate: str | None
  authoritative_main: str
  current: bool


def _repository_settings(config: dict) -> tuple[str, str]:
  repository = config["repository"]
  return repository["authoritativeRemote"], repository["integrationBranch"]


def authoritative_main_sha(root: Path, config: dict, *, fetch: bool = True) -> str:
  remote, integration_branch = _repository_settings(config)
  if fetch:
    git(
      root,
      "fetch",
      "--no-tags",
      remote,
      f"refs/heads/{integration_branch}:refs/remotes/{remote}/{integration_branch}",
    )
  result = git(
    root,
    "ls-remote",
    "--heads",
    remote,
    f"refs/heads/{integration_branch}",
    check=False,
  )
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise PrelimError(f"cannot read authoritative integration branch: {detail}")
  lines = [line for line in result.stdout.splitlines() if line.strip()]
  if len(lines) != 1 or "\t" not in lines[0]:
    raise PrelimError("authoritative integration branch is unavailable")
  return lines[0].split("\t", 1)[0].strip()


def _local_branch_sha(root: Path, branch: str) -> str | None:
  result = git(root, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)
  if result.returncode:
    return None
  value = result.stdout.strip()
  return value or None


def _require_clean(root: Path) -> None:
  changes = changed_files(root)
  if changes:
    raise PrelimError(
      "preliminary integration requires a clean checkout: " + ", ".join(changes)
    )


def prelim_status(root: Path, config: dict) -> PrelimStatus:
  root = root.resolve()
  authoritative = authoritative_main_sha(root, config)
  candidate = _local_branch_sha(root, PRELIM_BRANCH)
  if candidate is None:
    return PrelimStatus(False, None, authoritative, False)
  ancestry = git(
    root,
    "merge-base",
    "--is-ancestor",
    authoritative,
    candidate,
    check=False,
  )
  return PrelimStatus(True, candidate, authoritative, ancestry.returncode == 0)


def start_prelim(root: Path, config: dict) -> str:
  root = root.resolve()
  _require_clean(root)
  if _local_branch_sha(root, PRELIM_BRANCH) is not None:
    raise PrelimError(f"{PRELIM_BRANCH} already exists")
  authoritative = authoritative_main_sha(root, config)
  git(root, "branch", PRELIM_BRANCH, authoritative)
  git(root, "switch", PRELIM_BRANCH)
  if head_sha(root) != authoritative:
    raise PrelimError("preliminary branch did not start at authoritative main")
  return authoritative


def merge_accepted(root: Path, source_ref: str) -> str:
  root = root.resolve()
  _require_clean(root)
  if current_branch(root) != PRELIM_BRANCH:
    raise PrelimError(f"accepted work may be integrated only on {PRELIM_BRANCH}")
  before = head_sha(root)
  result = git(root, "rev-parse", "--verify", source_ref, check=False)
  if result.returncode:
    raise PrelimError(f"accepted source ref is unavailable: {source_ref}")
  git(
    root,
    "merge",
    "--no-ff",
    source_ref,
    "-m",
    f"chore(workflow): integrate accepted {source_ref}",
  )
  after = head_sha(root)
  if after == before:
    raise PrelimError("accepted integration produced no new candidate")
  return after


def reintegrate_prelim(root: Path, config: dict) -> str:
  root = root.resolve()
  _require_clean(root)
  status = prelim_status(root, config)
  if not status.present or status.candidate is None:
    raise PrelimError(f"{PRELIM_BRANCH} does not exist")
  if status.current:
    raise PrelimError("preliminary candidate is already based on current main")
  if current_branch(root) != PRELIM_BRANCH:
    git(root, "switch", PRELIM_BRANCH)
  before = head_sha(root)
  git(
    root,
    "merge",
    "--no-ff",
    status.authoritative_main,
    "-m",
    "chore(workflow): reintegrate authoritative main",
  )
  after = head_sha(root)
  if after == before:
    raise PrelimError("reintegration produced no new candidate")
  refreshed = prelim_status(root, config)
  if not refreshed.current:
    raise PrelimError("reintegrated candidate is still stale")
  return after


def create_prelim_tag(
  root: Path,
  config: dict,
  *,
  issue: int,
  integration_generation: int,
  validation_iteration: int,
  push: bool = False,
) -> str:
  root = root.resolve()
  _require_clean(root)
  if current_branch(root) != PRELIM_BRANCH:
    raise PrelimError(f"PRELIM tags may be created only on {PRELIM_BRANCH}")
  if issue < 1 or integration_generation < 0 or validation_iteration < 1:
    raise PrelimError("invalid PRELIM tag identity")
  version = read_stable_version(root, config)
  tag = (
    f"v{version}-PRELIM-{issue}."
    f"{integration_generation}.{validation_iteration}"
  )
  local = git(root, "rev-parse", "--verify", f"refs/tags/{tag}", check=False)
  if local.returncode == 0:
    raise PrelimError(f"PRELIM tag already exists: {tag}")
  remote, _integration_branch = _repository_settings(config)
  published = git(
    root,
    "ls-remote",
    "--tags",
    remote,
    f"refs/tags/{tag}",
    check=False,
  )
  if published.returncode:
    detail = (published.stderr or published.stdout).strip()
    raise PrelimError(f"cannot establish PRELIM tag state: {detail}")
  if published.stdout.strip():
    raise PrelimError(f"PRELIM tag already exists remotely: {tag}")
  git(root, "tag", "-a", tag, head_sha(root), "-m", tag)
  if push:
    git(root, "push", remote, f"refs/tags/{tag}")
  return tag


def _same_tree(root: Path, left: str, right: str) -> bool:
  result = git(root, "diff", "--quiet", left, right, "--", check=False)
  return result.returncode == 0


def retire_prelim(root: Path, config: dict) -> str:
  root = root.resolve()
  _require_clean(root)
  status = prelim_status(root, config)
  if not status.present or status.candidate is None:
    raise PrelimError(f"{PRELIM_BRANCH} does not exist")
  integrated = git(
    root,
    "merge-base",
    "--is-ancestor",
    status.candidate,
    status.authoritative_main,
    check=False,
  ).returncode == 0
  if not integrated and not _same_tree(root, status.candidate, status.authoritative_main):
    raise PrelimError("server main does not yet contain the preliminary candidate")

  _remote, integration_branch = _repository_settings(config)
  local_main = _local_branch_sha(root, integration_branch)
  if local_main is None:
    raise PrelimError(f"local {integration_branch} does not exist")
  ff = git(
    root,
    "merge-base",
    "--is-ancestor",
    local_main,
    status.authoritative_main,
    check=False,
  )
  if ff.returncode:
    raise PrelimError(f"local {integration_branch} cannot fast-forward to server main")
  if current_branch(root) != integration_branch:
    git(root, "switch", integration_branch)
  git(root, "merge", "--ff-only", status.authoritative_main)
  git(root, "branch", "-D", PRELIM_BRANCH)
  return head_sha(root)
