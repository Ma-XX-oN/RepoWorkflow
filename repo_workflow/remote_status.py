"""Provider-neutral read-only CMD status and conservative polling.

No provider-specific API, result publication, or automatic retry lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess
import time
from uuid import uuid4

from .config import load_config
from .remote_result import PublishedResult, RemoteResultError, read_result
from .repo_info_adapter import RepoInfoError, ci_invocation_status, resolve_info_config


PENDING_EXIT = 75
_CMD = re.compile(r"CMD-([1-9][0-9]*)-(.+)\Z")
_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_RETRY = re.compile(r"0|[1-9][0-9]*\Z")


class RemoteStatusError(RuntimeError):
  """Invalid selection, request, polling options, or unstable CMD identity."""


@dataclass(frozen=True)
class CommandRef:
  number: int
  branch: str
  tip: str


@dataclass(frozen=True)
class CommandStatus:
  number: int
  branch: str
  request_sha: str
  retry: int
  state: str
  result: PublishedResult | None
  provider_run_id: int | None


def _git(root: Path, *args: str) -> str:
  try:
    done = subprocess.run(
      ["git", *args], cwd=root, capture_output=True, check=False,
    )
  except OSError as exc:
    raise RemoteStatusError(f"cannot run Git: {exc}") from exc
  try:
    stdout = done.stdout.decode("utf-8", errors="strict")
    stderr = done.stderr.decode("utf-8", errors="strict")
  except UnicodeError as exc:
    raise RemoteStatusError("Git output is not valid UTF-8") from exc
  if done.returncode:
    raise RemoteStatusError(
      f"Git {args[0]} failed: {(stderr or stdout).strip()}"
    )
  return stdout.strip()


def _refs(root: Path, remote: str) -> list[CommandRef]:
  if not isinstance(remote, str) or not re.fullmatch(
    r"[a-zA-Z0-9._/-]+", remote
  ) or remote.startswith("-"):
    raise RemoteStatusError("invalid remote name")
  found: dict[int, CommandRef] = {}
  for line in _git(root, "ls-remote", "--heads", remote).splitlines():
    parts = line.split("\t")
    if len(parts) != 2 or not _SHA.fullmatch(parts[0]) or not parts[1].startswith("refs/heads/"):
      raise RemoteStatusError("invalid remote branch advertisement")
    branch = parts[1].removeprefix("refs/heads/")
    match = _CMD.fullmatch(branch)
    if match is None:
      continue
    number = int(match.group(1))
    if number in found:
      raise RemoteStatusError(f"ambiguous CMD number {number}")
    found[number] = CommandRef(number, branch, parts[0])
  return sorted(found.values(), key=lambda item: item.number)


def resolve_command(root: Path, selection: int | None = None, *,
                    remote: str = "origin") -> CommandRef:
  refs = _refs(root, remote)
  if not refs:
    raise RemoteStatusError("no numbered CMD requests exist")
  if selection is None:
    return refs[-1]
  if type(selection) is not int or selection == 0:
    raise RemoteStatusError("CMD selector must be a nonzero integer")
  if selection < 0:
    try:
      return refs[selection]
    except IndexError as exc:
      raise RemoteStatusError("relative CMD selector is out of range") from exc
  for item in refs:
    if item.number == selection:
      return item
  raise RemoteStatusError(f"CMD-{selection} does not exist")


def _marker(root: Path, selected: CommandRef, remote: str) -> tuple[str, int]:
  ref = f"refs/rwf/status-inspect/{uuid4().hex}"
  try:
    _git(root, "fetch", "--no-tags", "--no-recurse-submodules", remote,
         f"refs/heads/{selected.branch}:{ref}")
    if _git(root, "rev-parse", f"{ref}^{{commit}}") != selected.tip:
      raise RemoteStatusError("CMD advanced during request inspection")
    request_sha = _git(root, "log", "-1", "--format=%H", ref, "--", ".ci/rwf")
    if not _SHA.fullmatch(request_sha):
      raise RemoteStatusError("CMD request commit is missing")
    raw = _git(root, "show", f"{request_sha}:.ci/rwf")
    try:
      words = shlex.split(raw, posix=True)
    except ValueError as exc:
      raise RemoteStatusError("CMD request argv is malformed") from exc
    if len(words) < 3 or words[-2] != "--remote" or _RETRY.fullmatch(words[-1]) is None:
      raise RemoteStatusError("CMD retry marker is malformed")
    changed = _git(root, "diff-tree", "--no-commit-id", "--name-only",
                   "-r", request_sha).splitlines()
    if changed != [".ci/rwf"]:
      raise RemoteStatusError("CMD request commit changed unexpected files")
    return request_sha, int(words[-1])
  finally:
    subprocess.run(
      ["git", "update-ref", "-d", ref], cwd=root, capture_output=True,
      check=False,
    )


def _tip_unchanged(root: Path, command: CommandRef, remote: str) -> None:
  current = next((item for item in _refs(root, remote)
                  if item.number == command.number), None)
  if current != command:
    raise RemoteStatusError("CMD changed while status was being read")


def command_status(root: Path, selection: int | None = None, *,
                   remote: str = "origin",
                   info_config: dict | None = None) -> CommandStatus:
  """Resolve current numbered attempt, read result, then check CI if pending.

  Absence of a result or a provider observation never proves invocation loss.
  """
  root = Path(root)
  cmd = resolve_command(root, selection, remote=remote)
  request_sha, retry = _marker(root, cmd, remote)
  try:
    completed = read_result(root, cmd.branch, remote=remote)
  except RemoteResultError as exc:
    raise RemoteStatusError(str(exc)) from exc
  if completed is not None:
    if completed.request_sha != request_sha or completed.retry != retry:
      raise RemoteStatusError("published result is for a stale attempt")
    _tip_unchanged(root, cmd, remote)
    return CommandStatus(
      cmd.number, cmd.branch, request_sha, retry, "completed",
      completed, None,
    )
  try:
    config = info_config if info_config is not None else resolve_info_config(
      root, load_config(root),
    )
    observation = ci_invocation_status(
      root, config, cmd.branch, request_sha, retry,
    )
  except RepoInfoError as exc:
    raise RemoteStatusError(f"provider status unavailable: {exc}") from exc
  _tip_unchanged(root, cmd, remote)
  return CommandStatus(
    cmd.number, cmd.branch, request_sha, retry,
    observation["state"], None, observation["run_id"],
  )


def parse_intervals(values: list[str] | None) -> tuple[float, ...] | None:
  if values is None:
    return None
  if not values:
    return (15.0,)
  intervals = []
  for token in values:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", token):
      raise RemoteStatusError("poll interval must be a nonnegative finite number")
    number = float(token)
    if not 0 <= number <= 86400:
      raise RemoteStatusError("poll interval must be between 0 and 86400 seconds")
    intervals.append(number)
  return tuple(intervals)


def _render(status: CommandStatus) -> int:
  if status.result is None:
    print(f"CMD-{status.number} {status.branch} PENDING ({status.state})")
    return PENDING_EXIT
  print(f"CMD-{status.number} {status.branch} COMPLETED exit={status.result.exit_code}")
  if status.result.output:
    print(status.result.output, end="")
  return status.result.exit_code


def remote_status(
  root: Path, selection: int | None = None,
  *, intervals: tuple[float, ...] | None = None, remote: str = "origin",
  info_config: dict | None = None, sleep=time.sleep,
) -> int:
  """Read once, or poll without mutation until completion.

  Exit 75 denotes PENDING for one-shot retrieval. Completed command code 75
  is preserved without remapping; the COMPLETED marker disambiguates it.
  """
  index = 0
  while True:
    status = command_status(root, selection, remote=remote,
                            info_config=info_config)
    if status.result is not None or intervals is None:
      return _render(status)
    sleep(intervals[min(index, len(intervals) - 1)])
    index += 1
