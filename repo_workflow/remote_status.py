"""Provider-neutral read-only CMD status and conservative polling.

No provider-specific API, result publication, or automatic retry lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from uuid import uuid4

from .config import ConfigError
from .remote_result import PublishedResult, RemoteResultError, read_result
from .repo_info_adapter import RepoInfoError, ci_invocation_status, resolve_info_config
from .remote_request import RemoteRequestError, submit_request


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


def _git(root: Path, *args: str, preserve_record: bool = False) -> str:
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
  return stdout if preserve_record else stdout.strip()


def _refs(root: Path, remote: str) -> list[CommandRef]:
  if not isinstance(remote, str) or not re.fullmatch(
    r"[a-zA-Z0-9._/-]+", remote
  ) or remote.startswith("-"):
    raise RemoteStatusError("invalid remote name")
  # CMD-N is scoped to the complete originating source-branch identity.
  source = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
  if _CMD.fullmatch(source):
    raise RemoteStatusError("remote-status requires a source branch")
  found: dict[str, CommandRef] = {}
  listing = _git(root, "ls-remote", "--heads", remote,
                 preserve_record=True)
  if listing and not listing.endswith("\n"):
    raise RemoteStatusError("unterminated remote ref listing")
  for line in listing[:-1].split("\n") if listing else ():
    parts = line.split("\t")
    if len(parts) != 2 or not _SHA.fullmatch(parts[0]) or not parts[1].startswith("refs/heads/"):
      raise RemoteStatusError("invalid remote branch advertisement")
    branch = parts[1].removeprefix("refs/heads/")
    match = _CMD.fullmatch(branch)
    if match is None or match.group(2) != source:
      continue
    number = int(match.group(1))
    if branch in found:
      raise RemoteStatusError(f"duplicate CMD branch {branch}")
    found[branch] = CommandRef(number, branch, parts[0])
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
                  if item.branch == command.branch), None)
  if current != command:
    raise RemoteStatusError("CMD changed while status was being read")


def _command_status_once(root: Path, selection: int | None = None, *,
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
    config = info_config if info_config is not None else resolve_info_config(root)
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


def command_status(root: Path, selection: int | None = None, *,
                   remote: str = "origin",
                   info_config: dict | None = None) -> CommandStatus:
  """Retry bounded read-only snapshots when a legitimate CMD tip advances."""
  for attempt in range(3):
    try:
      return _command_status_once(
        root, selection, remote=remote, info_config=info_config,
      )
    except RemoteStatusError as exc:
      if (str(exc) not in (
        "CMD advanced during request inspection",
        "CMD changed while status was being read",
        "CMD branch advanced during result inspection",
      ) or attempt == 2):
        raise
  raise RemoteStatusError("CMD changed repeatedly during status inspection")


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


def _configure_utf8_output() -> None:
  # Explicit UTF-8/LF for every public CMD status or submission stream.
  for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
      stream.reconfigure(encoding="utf-8", errors="strict", newline="\n")


def _render(status: CommandStatus) -> int:
  _configure_utf8_output()
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
  expected_request: str | None = None,
) -> int:
  """Read once, or poll without mutation until completion.

  Exit 75 denotes PENDING for one-shot retrieval. Completed command code 75
  is preserved without remapping; the COMPLETED marker disambiguates it.
  """
  _configure_utf8_output()
  index = 0
  while True:
    status = command_status(root, selection, remote=remote,
                            info_config=info_config)
    if expected_request is not None and status.request_sha != expected_request:
      raise RemoteStatusError("polled CMD was superseded by another attempt")
    if status.result is not None or intervals is None:
      return _render(status)
    sleep(intervals[min(index, len(intervals) - 1)])
    index += 1

def submit_remote(
  root: Path, argv: list[str], *,
  intervals: tuple[float, ...] | None = None, remote: str = "origin",
  clock=time.time, status_reader=command_status,
) -> int:
  """Submit a public numbered CMD, reuse identical requests, never guess loss.

  The accepted provider adapter has no terminal non-execution proof or
  executor-fencing token. Thus it cannot authorize a retry of an attempt.
  Repeated requests always reuse the prior CMD; no retry commit is written.
  """
  _configure_utf8_output()
  try:
    request = submit_request(root, argv, remote=remote)
  except RemoteRequestError as exc:
    print(f"Remote request rejected: {exc}", file=sys.stderr)
    return 1
  print(
    f"CMD-{request.number} {request.branch} "
    + ("REUSED" if request.reused else "SUBMITTED")
  )
  if intervals is not None:
    return remote_status(
      root, request.number, intervals=intervals, remote=remote,
      expected_request=request.request_sha,
    )
  if request.reused:
    # At 15 seconds check status; never confuse an absent result or a
    # provider-not-observed response with permission to submit another attempt.
    try:
      submitted_at = float(_git(
        Path(root), "show", "-s", "--format=%ct", request.request_sha,
      ))
      if clock() - submitted_at >= 15:
        observation = status_reader(root, request.number, remote=remote)
        if observation.request_sha != request.request_sha:
          raise RemoteStatusError("reused request advanced during inspection")
        if observation.result is None:
          print(f"CMD-{request.number} {request.branch} PENDING ({observation.state})")
    except (ValueError, RemoteStatusError, ConfigError) as exc:
      # The request was already accepted/reused; status uncertainty must
      # never create another remote execution or falsify acceptance.
      print(f"CMD-{request.number} status UNKNOWN: {exc}", file=sys.stderr)
  return 0
