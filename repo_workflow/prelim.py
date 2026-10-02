from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import uuid

from .git import changed_files, current_branch, git, head_sha
from .version_adapter import read_stable_version


PRELIM_PREFIX = "prelim-main-"


class PrelimError(RuntimeError):
  pass


@dataclass(frozen=True)
class PrelimStatus:
  branch: str
  attempt_id: str
  present: bool
  candidate: str | None
  authoritative_main: str
  current: bool


def prelim_branch(attempt_id: str) -> str:
  try:
    normalized = str(uuid.UUID(attempt_id))
  except ValueError as exc:
    raise PrelimError(f"invalid preliminary integration GUID: {attempt_id}") from exc
  return PRELIM_PREFIX + normalized


def prelim_attempt_id(branch: str) -> str | None:
  if not branch.startswith(PRELIM_PREFIX):
    return None
  value = branch[len(PRELIM_PREFIX):]
  try:
    normalized = str(uuid.UUID(value))
  except ValueError:
    return None
  if value != normalized:
    return None
  return normalized


def is_prelim_branch(branch: str) -> bool:
  return prelim_attempt_id(branch) is not None


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


def _git_dir(root: Path) -> Path:
  value = git(root, "rev-parse", "--git-dir").stdout.strip()
  path = Path(value)
  return path if path.is_absolute() else (root / path).resolve()


def _attempt_path(root: Path, attempt_id: str) -> Path:
  return _git_dir(root) / "repoworkflow" / "prelim" / f"{attempt_id}.json"


def _write_attempt(root: Path, attempt_id: str, branch: str) -> None:
  path = _attempt_path(root, attempt_id)
  path.parent.mkdir(parents=True, exist_ok=True)
  if path.exists():
    raise PrelimError(f"preliminary integration attempt already exists: {attempt_id}")
  path.write_text(
    json.dumps({"attemptId": attempt_id, "branch": branch}, sort_keys=True) + "\n",
    encoding="utf-8",
  )


def _require_owned_attempt(root: Path, branch: str) -> str:
  attempt_id = prelim_attempt_id(branch)
  if attempt_id is None:
    raise PrelimError(f"not a GUID-qualified preliminary branch: {branch}")
  path = _attempt_path(root, attempt_id)
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except (FileNotFoundError, json.JSONDecodeError) as exc:
    raise PrelimError(
      f"preliminary integration branch is not owned by this clone: {branch}"
    ) from exc
  if value != {"attemptId": attempt_id, "branch": branch}:
    raise PrelimError(f"invalid preliminary integration record: {path}")
  return attempt_id


def _resolve_branch(root: Path, branch: str | None) -> str:
  value = branch or current_branch(root)
  if not is_prelim_branch(value):
    raise PrelimError("current branch is not a GUID-qualified preliminary integration")
  _require_owned_attempt(root, value)
  return value


def prelim_status(
  root: Path,
  config: dict,
  branch: str | None = None,
) -> PrelimStatus:
  root = root.resolve()
  branch = _resolve_branch(root, branch)
  attempt_id = _require_owned_attempt(root, branch)
  authoritative = authoritative_main_sha(root, config)
  candidate = _local_branch_sha(root, branch)
  if candidate is None:
    return PrelimStatus(branch, attempt_id, False, None, authoritative, False)
  ancestry = git(
    root,
    "merge-base",
    "--is-ancestor",
    authoritative,
    candidate,
    check=False,
  )
  return PrelimStatus(
    branch,
    attempt_id,
    True,
    candidate,
    authoritative,
    ancestry.returncode == 0,
  )


def start_prelim(
  root: Path,
  config: dict,
  *,
  attempt_id: str | None = None,
) -> PrelimStatus:
  root = root.resolve()
  _require_clean(root)
  attempt_id = str(uuid.UUID(attempt_id)) if attempt_id else str(uuid.uuid4())
  branch = prelim_branch(attempt_id)
  if _local_branch_sha(root, branch) is not None:
    raise PrelimError(f"{branch} already exists")
  if _attempt_path(root, attempt_id).exists():
    raise PrelimError(f"preliminary integration attempt already exists: {attempt_id}")
  authoritative = authoritative_main_sha(root, config)
  git(root, "branch", branch, authoritative)
  _write_attempt(root, attempt_id, branch)
  try:
    git(root, "switch", branch)
  except Exception:
    git(root, "branch", "-D", branch, check=False)
    _attempt_path(root, attempt_id).unlink(missing_ok=True)
    raise
  if head_sha(root) != authoritative:
    raise PrelimError("preliminary branch did not start at authoritative main")
  return PrelimStatus(branch, attempt_id, True, authoritative, authoritative, True)


def merge_accepted(root: Path, source_ref: str) -> str:
  root = root.resolve()
  _require_clean(root)
  branch = _resolve_branch(root, None)
  if current_branch(root) != branch:
    raise PrelimError(f"accepted work may be integrated only on {branch}")
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


def reintegrate_prelim(root: Path, config: dict, branch: str | None = None) -> str:
  root = root.resolve()
  _require_clean(root)
  branch = _resolve_branch(root, branch)
  status = prelim_status(root, config, branch)
  if not status.present or status.candidate is None:
    raise PrelimError(f"{branch} does not exist")
  if status.current:
    raise PrelimError("preliminary candidate is already based on current main")
  if current_branch(root) != branch:
    git(root, "switch", branch)
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
  refreshed = prelim_status(root, config, branch)
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
  _resolve_branch(root, None)
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


def retire_prelim(
  root: Path,
  config: dict,
  branch: str | None = None,
) -> str:
  root = root.resolve()
  _require_clean(root)
  branch = _resolve_branch(root, branch)
  status = prelim_status(root, config, branch)
  if not status.present or status.candidate is None:
    raise PrelimError(f"{branch} does not exist")
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

  remote, integration_branch = _repository_settings(config)
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

  published = git(
    root,
    "ls-remote",
    "--heads",
    remote,
    f"refs/heads/{branch}",
    check=False,
  )
  if published.returncode:
    raise PrelimError("cannot establish remote preliminary branch state")
  if published.stdout.strip():
    git(root, "push", remote, "--delete", branch)

  if current_branch(root) != integration_branch:
    git(root, "switch", integration_branch)
  git(root, "merge", "--ff-only", status.authoritative_main)
  git(root, "branch", "-D", branch)
  _attempt_path(root, status.attempt_id).unlink(missing_ok=True)
  return head_sha(root)
