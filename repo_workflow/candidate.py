from __future__ import annotations

from pathlib import Path
import re

from .git import changed_files, git, git_bytes, git_wire_path, head_sha, repository_state, restore_repository_state
from .guard import Candidate, GuardError, validate_candidate
from .source_tip import source_tip
from .version_evidence import tested_source_changed
from .version_adapter import (
  VersionAdapterError,
  read_development_version,
  run_transition,
)


_VERSION_PARTS_RE = re.compile(
  r"^(?P<base>\d+\.\d+\.\d+)-issue\."
  r"(?P<issue>\d+)\.(?P<generation>\d+)\.(?P<iteration>\d+)$"
)


def _assert_implementation_advanced(before: str, after: str) -> None:
  """Require Q+1/R=0 while preserving the stable base and issue identity."""
  before_match = _VERSION_PARTS_RE.fullmatch(before)
  after_match = _VERSION_PARTS_RE.fullmatch(after)
  if before_match is None or after_match is None:
    raise GuardError("repository version adapter produced an invalid task version")
  expected = {
    "base": before_match.group("base"),
    "issue": before_match.group("issue"),
    "generation": str(int(before_match.group("generation")) + 1),
    "iteration": "0",
  }
  actual = {name: after_match.group(name) for name in expected}
  if actual != expected:
    raise GuardError(
      "repository version adapter did not prepare exactly one implementation revision: "
      f"{before} -> {after}"
    )


def _advance_implementation(root: Path, config: dict, version: str) -> str:
  """Prepare the next implementation revision through the consumer adapter."""
  try:
    run_transition(root, config, "task", "--increment", "merge-integration-failed")
    advanced = read_development_version(root, config)
  except VersionAdapterError as exc:
    raise GuardError(str(exc)) from exc
  _assert_implementation_advanced(version, advanced)
  return advanced


def _request_commit(root: Path) -> str | None:
  result = git(
    root,
    "log",
    "-1",
    "--format=%H",
    "--",
    ".ci/run-ci-request",
    check=False,
  )
  value = result.stdout.strip()
  return value or None


def _request_needs_refresh(root: Path, config: dict, version: str) -> bool:
  path = root / ".ci" / "run-ci-request"
  try:
    requested = path.read_text(encoding="utf-8").strip()
  except FileNotFoundError:
    return True
  if requested != version:
    return True
  request_commit = _request_commit(root)
  if request_commit is None:
    return True
  head = head_sha(root)
  if request_commit == head:
    return False
  if source_tip(root) == source_tip(root, request_commit):
    return False
  ancestry = git(
    root,
    "merge-base",
    "--is-ancestor",
    request_commit,
    head,
    check=False,
  )
  if ancestry.returncode:
    return True
  allowed = {
    path
    for artifact in config.get("artifacts", [])
    if artifact.get("committed", True)
    for path in artifact.get("outputs", [])
  }
  raw = git_bytes(
    root, "log", "--format=", "--name-only", "-z",
    f"{request_commit}..{head}",
  ).stdout
  if raw and not raw.endswith(b"\0"):
    raise GuardError("unterminated Git history path record")
  changed = {git_wire_path(item) for item in raw.split(b"\0") if item}
  return bool(changed - allowed)


def _refresh_request_file(root: Path, version: str) -> None:
  request = root / ".ci" / "run-ci-request"
  request.parent.mkdir(parents=True, exist_ok=True)
  try:
    current = request.read_text(encoding="utf-8")
  except FileNotFoundError:
    current = ""
  canonical = version + "\n"
  alternate = version + "\n\n"
  target = alternate if current == canonical else canonical
  request.write_text(target, encoding="utf-8")


def prepare_development_candidate(
  root: Path,
  config: dict,
  *,
  push: bool = False,
  parent_reintegration: bool = False,
) -> tuple[Candidate, bool]:
  root = root.resolve()
  if changed_files(root):
    raise GuardError(
      "candidate checkout is not clean; commit or discard source changes before verify"
    )
  before = repository_state(root)
  remote = config["repository"]["authoritativeRemote"]
  prepared = False
  try:
    try:
      version = read_development_version(root, config)
    except VersionAdapterError as exc:
      raise GuardError(str(exc)) from exc
    issue = int(_VERSION_PARTS_RE.fullmatch(version).group("issue"))
    if parent_reintegration:
      run_transition(root, config, "task", "--increment", "CI-iteration")
      version = read_development_version(root, config)
      prepared = True
    while not parent_reintegration and tested_source_changed(root, issue, version, remote=remote):
      version = _advance_implementation(root, config, version)
      prepared = True

    if _request_needs_refresh(root, config, version):
      _refresh_request_file(root, version)
      prepared = True

    if prepared:
      paths = changed_files(root)
      if not paths:
        raise GuardError("candidate preparation produced no bookkeeping changes")
      git(root, "add", "--all")
      git(
        root,
        "commit",
        "-m",
        f"chore(workflow): prepare authoritative validation for {version}",
      )

    candidate = validate_candidate(root, config)
    if push:
      branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
      if not branch or branch == "HEAD":
        raise GuardError("cannot push prepared candidate from detached HEAD")
      git(root, "push", remote, f"HEAD:{branch}")
    return candidate, prepared
  except Exception:
    restore_repository_state(root, before)
    raise
