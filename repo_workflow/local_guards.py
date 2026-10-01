from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from .config import load_config
from .git import changed_files, current_branch, git
from .prelim import PRELIM_BRANCH, PrelimError, prelim_status
from .workflow_state import discover_facts


_ZERO_OID_RE = re.compile(r"^0+$")
_STABLE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_TASK_TAG_RE = re.compile(
  r"^v\d+\.\d+\.\d+-issue\.\d+\.\d+\.\d+(?:-CI-FAIL)?$"
)
_PRELIM_TAG_RE = re.compile(
  r"^v\d+\.\d+\.\d+-PRELIM-\d+\.\d+\.\d+$"
)


class LocalGuardError(RuntimeError):
  pass


@dataclass(frozen=True)
class PushUpdate:
  local_ref: str
  local_oid: str
  remote_ref: str
  remote_oid: str

  @property
  def deleting(self) -> bool:
    return bool(_ZERO_OID_RE.fullmatch(self.local_oid))

  @property
  def creating(self) -> bool:
    return bool(_ZERO_OID_RE.fullmatch(self.remote_oid))


def parse_push_updates(text: str) -> list[PushUpdate]:
  updates: list[PushUpdate] = []
  for line_number, line in enumerate(text.splitlines(), start=1):
    if not line.strip():
      continue
    fields = line.split()
    if len(fields) != 4:
      raise LocalGuardError(f"invalid pre-push input on line {line_number}")
    updates.append(PushUpdate(*fields))
  return updates


def _integration_branch(config: dict) -> str:
  return config["repository"]["integrationBranch"]


def _assert_current_state(root: Path) -> None:
  facts = discover_facts(root)
  if not facts.branch_valid:
    raise LocalGuardError("current branch is invalid for RepoWorkflow")
  if not facts.version_valid:
    raise LocalGuardError("current repository version state is invalid")


def check_commit(root: Path) -> None:
  root = root.resolve()
  config = load_config(root)
  branch = current_branch(root)
  if branch == _integration_branch(config):
    raise LocalGuardError(
      f"direct commits on tracking {_integration_branch(config)} are blocked; "
      f"use {PRELIM_BRANCH} for integration work"
    )
  _assert_current_state(root)


def _check_tag_update(update: PushUpdate) -> None:
  tag = update.remote_ref.removeprefix("refs/tags/")
  if update.deleting:
    if (
      _STABLE_TAG_RE.fullmatch(tag)
      or _TASK_TAG_RE.fullmatch(tag)
      or _PRELIM_TAG_RE.fullmatch(tag)
    ):
      raise LocalGuardError(f"immutable workflow tag may not be deleted: {tag}")
    return

  if _STABLE_TAG_RE.fullmatch(tag):
    raise LocalGuardError(
      f"stable tag {tag} may only be created by the protected server finalizer"
    )
  if _TASK_TAG_RE.fullmatch(tag) or _PRELIM_TAG_RE.fullmatch(tag):
    if not update.creating and update.local_oid != update.remote_oid:
      raise LocalGuardError(f"immutable workflow tag may not be moved: {tag}")
    return
  if tag.startswith("v"):
    raise LocalGuardError(f"malformed or unauthorized workflow tag: {tag}")


def check_push(root: Path, input_text: str) -> None:
  root = root.resolve()
  config = load_config(root)
  integration_branch = _integration_branch(config)
  current = current_branch(root)
  updates = parse_push_updates(input_text)

  for update in updates:
    if update.remote_ref == f"refs/heads/{integration_branch}":
      raise LocalGuardError(
        f"direct push/update/delete of protected {integration_branch} is blocked"
      )
    if update.remote_ref.startswith("refs/tags/"):
      _check_tag_update(update)
    if update.remote_ref == f"refs/heads/{PRELIM_BRANCH}" and not update.deleting:
      try:
        status = prelim_status(root, config)
      except PrelimError as exc:
        raise LocalGuardError(str(exc)) from exc
      if not status.present or status.candidate is None:
        raise LocalGuardError(f"{PRELIM_BRANCH} does not exist locally")
      if update.local_oid != status.candidate:
        raise LocalGuardError("pre-push candidate does not match local prelim-main")
      if not status.current:
        raise LocalGuardError("stale prelim-main must be reintegrated before push")

  current_ref = f"refs/heads/{current}"
  if any(update.local_ref == current_ref and not update.deleting for update in updates):
    _assert_current_state(root)


def _terminal_tag(tag: str) -> bool:
  return bool(
    _TASK_TAG_RE.fullmatch(tag)
    or _PRELIM_TAG_RE.fullmatch(tag)
    or _STABLE_TAG_RE.fullmatch(tag)
  )


def check_rebase(root: Path, upstream: str, branch: str | None = None) -> None:
  root = root.resolve()
  config = load_config(root)
  target_branch = branch or current_branch(root)
  if target_branch == _integration_branch(config):
    raise LocalGuardError(f"rebasing tracking {_integration_branch(config)} is blocked")

  commits = {
    value.strip()
    for value in git(root, "rev-list", f"{upstream}..{target_branch}").stdout.splitlines()
    if value.strip()
  }
  if not commits:
    return
  for tag in git(root, "tag", "--merged", target_branch).stdout.splitlines():
    tag = tag.strip()
    if not tag or not _terminal_tag(tag):
      continue
    commit = git(root, "rev-list", "-n", "1", tag).stdout.strip()
    if commit in commits:
      raise LocalGuardError(
        f"rebase would rewrite tagged workflow candidate {tag} ({commit})"
      )


def _hook_dir(root: Path) -> Path:
  value = git(root, "rev-parse", "--git-dir").stdout.strip()
  git_dir = Path(value)
  if not git_dir.is_absolute():
    git_dir = (root / git_dir).resolve()
  return git_dir / "hooks"


def install_hooks(root: Path, *, force: bool = False) -> list[Path]:
  root = root.resolve()
  templates = Path(__file__).resolve().parents[1] / "templates" / "hooks"
  destination = _hook_dir(root)
  destination.mkdir(parents=True, exist_ok=True)
  installed: list[Path] = []
  for name in ("pre-commit", "pre-push", "pre-rebase"):
    source = templates / name
    target = destination / name
    if target.exists() and target.read_bytes() != source.read_bytes() and not force:
      raise LocalGuardError(
        f"existing hook differs: {target}; rerun install with --force to replace it"
      )
    shutil.copyfile(source, target)
    target.chmod(0o755)
    installed.append(target)
  return installed
