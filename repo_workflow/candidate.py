from __future__ import annotations

from pathlib import Path
import re

from .git import changed_files, git, head_sha, repository_state, restore_repository_state
from .guard import Candidate, GuardError, VERSION_RE, validate_candidate
from .process import run_command


_VERSION_PARTS_RE = re.compile(
  r"^(?P<base>\d+\.\d+\.\d+)-issue\.(?P<issue>\d+)\.(?P<iteration>\d+)$"
)


def _reported_version(root: Path, config: dict) -> str:
  before = repository_state(root)
  result = run_command(config["versionCommand"], root)
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise GuardError(f"repository version command failed: {detail}")
  lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
  if len(lines) != 1 or not VERSION_RE.fullmatch(lines[0]):
    raise GuardError("version command must print exactly one valid development version")
  after = repository_state(root)
  if after.commit != before.commit:
    raise GuardError("repository version command modified candidate history")
  if after.head_ref != before.head_ref:
    raise GuardError("repository version command modified HEAD reference")
  if after.refs != before.refs:
    raise GuardError("repository version command modified local Git refs")
  return lines[0]


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


def _next_iteration(version: str) -> str:
  match = _VERSION_PARTS_RE.fullmatch(version)
  if match is None:
    raise GuardError(f"cannot advance invalid development version: {version}")
  return (
    f"{match.group('base')}-issue.{match.group('issue')}."
    f"{int(match.group('iteration')) + 1}"
  )


def _set_version(root: Path, config: dict, version: str) -> None:
  command = config.get("setVersionCommand")
  if command is None:
    raise GuardError(
      "development iteration is consumed and setVersionCommand is not configured"
    )
  before = repository_state(root)
  result = run_command([*command, version], root)
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise GuardError(f"repository version setter failed: {detail}")
  after = repository_state(root)
  if after.commit != before.commit:
    raise GuardError("repository version setter modified candidate history")
  if after.head_ref != before.head_ref:
    raise GuardError("repository version setter modified HEAD reference")
  if after.refs != before.refs:
    raise GuardError("repository version setter modified local Git refs")
  reported = _reported_version(root, config)
  if reported != version:
    raise GuardError(
      f"repository version setter produced {reported}, expected {version}"
    )


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
    version = _reported_version(root, config)
    consumed = _terminal_tag(root, remote, version)
    if consumed is not None:
      version = _next_iteration(version)
      _set_version(root, config, version)
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
      if push:
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if not branch or branch == "HEAD":
          raise GuardError("cannot push prepared candidate from detached HEAD")
        git(root, "push", remote, f"HEAD:{branch}")

    return validate_candidate(root, config), prepared
  except Exception:
    restore_repository_state(root, before)
    raise
