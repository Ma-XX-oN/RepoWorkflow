from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .git import git, head_sha, repository_state
from .process import run_command


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+-issue\.\d+\.\d+$")


class GuardError(RuntimeError):
  pass


@dataclass(frozen=True)
class Candidate:
  version: str
  commit: str
  remote: str


def _request_version(root: Path) -> str:
  path = root / ".ci" / "run-ci-request"
  try:
    value = path.read_text(encoding="utf-8").strip()
  except FileNotFoundError as exc:
    raise GuardError(".ci/run-ci-request is missing") from exc
  if not VERSION_RE.fullmatch(value):
    raise GuardError(f"invalid CI request version: {value}")
  return value


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


def _assert_clean_full_checkout(root: Path) -> None:
  inside = git(root, "rev-parse", "--is-inside-work-tree", check=False)
  if inside.returncode or inside.stdout.strip() != "true":
    raise GuardError("candidate is not a Git working tree")
  shallow = git(root, "rev-parse", "--is-shallow-repository", check=False)
  if shallow.returncode or shallow.stdout.strip() != "false":
    raise GuardError("candidate requires a complete non-shallow checkout")
  status = git(
    root,
    "status",
    "--porcelain=v1",
    "--untracked-files=all",
  ).stdout
  if status:
    raise GuardError("candidate checkout is not clean:\n" + status.rstrip())


def _refresh_and_check_tags(root: Path, remote: str, version: str) -> None:
  remote_result = git(root, "remote", "get-url", remote, check=False)
  if remote_result.returncode or not remote_result.stdout.strip():
    raise GuardError(f"authoritative remote is unavailable: {remote}")
  tags = (f"v{version}", f"v{version}-CI-FAIL")
  refs = [f"refs/tags/{tag}" for tag in tags]
  remote_tags = git(root, "ls-remote", "--tags", remote, *refs, check=False)
  if remote_tags.returncode:
    detail = (remote_tags.stderr or remote_tags.stdout).strip()
    raise GuardError(f"cannot establish authoritative tag state: {detail}")
  present = {
    line.split("\t", 1)[1].strip()
    for line in remote_tags.stdout.splitlines()
    if "\t" in line
  }
  for tag, ref in zip(tags, refs):
    if ref in present:
      raise GuardError(f"development iteration already has terminal result tag: {tag}")
    local = git(root, "show-ref", "--verify", ref, check=False)
    if local.returncode == 0:
      git(root, "update-ref", "-d", ref)


def _assert_request_bound_to_candidate(
  root: Path,
  config: dict,
  head: str,
) -> None:
  request_commit_result = git(
    root,
    "log",
    "-1",
    "--format=%H",
    "--",
    ".ci/run-ci-request",
    check=False,
  )
  request_commit = request_commit_result.stdout.strip()
  if request_commit_result.returncode or not request_commit:
    raise GuardError("cannot establish the commit that requested CI")
  if request_commit == head:
    return
  ancestry = git(
    root,
    "merge-base",
    "--is-ancestor",
    request_commit,
    head,
    check=False,
  )
  if ancestry.returncode:
    raise GuardError("CI request commit is not an ancestor of the candidate")
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
  unexpected = sorted(changed - allowed)
  if unexpected:
    raise GuardError(
      "candidate contains changes after the CI request outside declared generated "
      "artifacts: " + ", ".join(unexpected)
    )


def validate_candidate(
  root: Path,
  config: dict,
  *,
  expected_sha: str | None = None,
) -> Candidate:
  root = root.resolve()
  _assert_clean_full_checkout(root)
  initial_commit = head_sha(root)
  request = _request_version(root)
  reported = _reported_version(root, config)
  _assert_clean_full_checkout(root)
  if head_sha(root) != initial_commit:
    raise GuardError("repository version command modified candidate history")
  if request != reported:
    raise GuardError(
      f"requested version {request} does not match repository version {reported}"
    )
  commit = head_sha(root)
  if expected_sha is not None and commit != expected_sha:
    raise GuardError(f"candidate commit {commit} does not match expected {expected_sha}")
  _assert_request_bound_to_candidate(root, config, commit)
  remote = config["repository"]["authoritativeRemote"]
  _refresh_and_check_tags(root, remote, request)
  return Candidate(request, commit, remote)
