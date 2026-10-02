from __future__ import annotations

from pathlib import Path
import re

from .git import changed_files, git, head_sha, repository_state, restore_repository_state
from .guard import Candidate, GuardError, validate_candidate
from .version_adapter import (
  VersionAdapterError,
  read_development_version,
  run_transition,
)


_VERSION_PARTS_RE = re.compile(
  r"^(?P<base>\d+\.\d+\.\d+)-issue\."
  r"(?P<issue>\d+)\.(?P<generation>\d+)\.(?P<iteration>\d+)$"
)


def _terminal_tag(root: Path, remote: str, version: str) -> str | None:
  remote_result = git(root, "remote", "get-url", remote, check=False)
  if remote_result.returncode or not remote_result.stdout.strip():
    raise GuardError(f"authoritative remote is unavailable: {remote}")
  tags = (f"v{version}", f"v{version}-CI-FAIL")
  refs = [f"refs/tags/{tag}" for tag in tags]
  result = git(root, "ls-remote", "--tags", remote, *refs, check=False)
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise GuardError(f"cannot establish authoritative tag state: {detail}")
  present = {
    line.split("\t", 1)[1].strip()
    for line in result.stdout.splitlines()
    if "\t" in line
  }
  for tag, ref in zip(tags, refs):
    if ref in present:
      return tag
  return None


def _assert_ci_iteration_advanced(before: str, after: str) -> None:
  before_match = _VERSION_PARTS_RE.fullmatch(before)
  after_match = _VERSION_PARTS_RE.fullmatch(after)
  if before_match is None or after_match is None:
    raise GuardError("repository version adapter produced an invalid task version")
  expected = {
    "base": before_match.group("base"),
    "issue": before_match.group("issue"),
    "generation": before_match.group("generation"),
    "iteration": str(int(before_match.group("iteration")) + 1),
  }
  actual = {name: after_match.group(name) for name in expected}
  if actual != expected:
    raise GuardError(
      "repository version adapter did not perform exactly one CI-iteration increment: "
      f"{before} -> {after}"
    )


def _advance_ci_iteration(root: Path, config: dict, version: str) -> str:
  try:
    run_transition(root, config, "task", "--increment", "CI-iteration")
    advanced = read_development_version(root, config)
  except VersionAdapterError as exc:
    raise GuardError(
      "repository version adapter did not perform exactly one "
      f"CI-iteration increment: {exc}"
    ) from exc
  _assert_ci_iteration_advanced(version, advanced)
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
    path.replace("\\", "/")
    for artifact in config.get("artifacts", [])
    if artifact.get("committed", True)
    for path in artifact.get("outputs", [])
  }
  changed = {
    line.strip().replace("\\", "/")
    for line in git(
      root,
      "log",
      "--format=",
      "--name-only",
      f"{request_commit}..{head}",
    ).stdout.splitlines()
    if line.strip()
  }
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
    consumed = _terminal_tag(root, remote, version)
    if consumed is not None:
      version = _advance_ci_iteration(root, config, version)
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
