"""Validate and execute numbered CMD requests through the existing CLI."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import traceback
from typing import Callable

from .git import current_branch, git, head_sha
from .command_grammar import CommandGrammarError, Context, parse_tokens
from .public_commands import COMMANDS


_CMD = re.compile(r"CMD-([1-9][0-9]*)-(.+)\Z")
_RETRY = re.compile(r"(0|[1-9][0-9]*)\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MARKER = ".ci/rwf"
_RESULT = ".repoworkflow/result"


class RemoteInvocationError(ValueError):
  """A CMD request failed validation before handler invocation."""


@dataclass(frozen=True)
class InvocationOutcome:
  branch: str
  request_sha: str
  source_sha: str
  retry: int
  exit_code: int
  stdout: str
  stderr: str
  output: str


@dataclass(frozen=True)
class _Request:
  branch: str
  source_branch: str
  source_sha: str
  request_sha: str
  retry: int
  argv: tuple[str, ...]


def _git(root: Path, *args: str) -> str:
  return git(root, *args).stdout.strip()


def _committed_marker(root: Path, commit: str) -> tuple[tuple[str, ...], int]:
  completed = subprocess.run(
    ["git", "show", f"{commit}:{_MARKER}"],
    cwd=root, capture_output=True, check=False,
  )
  if completed.returncode:
    raise RemoteInvocationError("missing committed .ci/rwf marker")
  try:
    raw = completed.stdout.decode("utf-8", errors="strict")
    words = shlex.split(raw, posix=True)
  except (UnicodeError, ValueError) as exc:
    raise RemoteInvocationError("invalid UTF-8 or quoting in .ci/rwf") from exc
  if raw not in {shlex.join(words), shlex.join(words) + "\n"}:
    raise RemoteInvocationError("noncanonical .ci/rwf argv serialization")
  if len(words) < 3 or words[-2] != "--remote":
    raise RemoteInvocationError("request lacks numbered --remote suffix")
  value = words[-1]
  if _RETRY.fullmatch(value) is None:
    raise RemoteInvocationError("retry count must be a nonnegative decimal integer")
  if "\x00" in raw:
    raise RemoteInvocationError("NUL byte in committed request")
  return tuple(words[:-2]), int(value)


def _assert_committed_result(root: Path, commit: str) -> None:
  completed = subprocess.run(
    ["git", "show", f"{commit}:{_RESULT}"],
    cwd=root, capture_output=True, check=False,
  )
  if completed.returncode:
    raise RemoteInvocationError("missing CMD result in publication commit")
  try:
    raw = completed.stdout.decode("utf-8", errors="strict")
  except UnicodeError as exc:
    raise RemoteInvocationError("CMD result must contain strict UTF-8") from exc
  status, separator, _ = raw.partition("\\n")
  if not separator or re.fullmatch(r"-?[0-9]+", status) is None:
    raise RemoteInvocationError("CMD result must begin with decimal exit code")


def _parent_and_paths(root: Path, commit: str) -> tuple[str, list[str]]:
  parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
  if len(parents) != 2:
    raise RemoteInvocationError("CMD transport commits must have one parent")
  paths = _git(
    root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit,
  ).splitlines()
  return parents[1], paths


def _remote_tip(root: Path, branch: str) -> str:
  completed = git(
    root, "ls-remote", "--heads", "origin", f"refs/heads/{branch}",
    check=False,
  )
  if completed.returncode:
    raise RemoteInvocationError("cannot verify authoritative remote branch tip")
  records = completed.stdout.splitlines()
  if len(records) != 1:
    raise RemoteInvocationError(f"remote branch missing or ambiguous: {branch}")
  parts = records[0].split()
  if len(parts) != 2 or parts[1] != f"refs/heads/{branch}":
    raise RemoteInvocationError("invalid authoritative branch advertisement")
  if _SHA.fullmatch(parts[0]) is None:
    raise RemoteInvocationError("invalid advertised Git revision")
  return parts[0]


def _validate(root: Path, argv: list[str]) -> _Request:
  branch = current_branch(root)
  match = _CMD.fullmatch(branch)
  if match is None:
    raise RemoteInvocationError("numbered --remote requires a CMD-N-source branch")
  if os.environ.get("RWF_HOSTED_INVOCATION") != "1":
    raise RemoteInvocationError("numbered --remote requires hosted invocation context")
  if len(argv) < 3 or argv[-2] != "--remote":
    raise RemoteInvocationError("numbered invocation marker is missing")
  if _RETRY.fullmatch(argv[-1]) is None:
    raise RemoteInvocationError("invalid numbered --remote retry count")

  tip = head_sha(root)
  if _remote_tip(root, branch) != tip:
    raise RemoteInvocationError("CMD checkout is stale or superseded")
  source_branch = match.group(2)
  source_tip = _remote_tip(root, source_branch)
  target_argv = tuple(argv[:-2])
  expected_retry = int(argv[-1])
  latest_retry = expected_retry
  current = tip
  first = True
  saw_request = False
  while True:
    parent, paths = _parent_and_paths(root, current)
    if paths == [_MARKER]:
      local_argv, retry = _committed_marker(root, current)
      if local_argv != target_argv or retry != expected_retry:
        raise RemoteInvocationError("CMD request identity or retry lineage mismatch")
      if first and retry != latest_retry:
        raise RemoteInvocationError("CMD marker retry mismatch")
      saw_request = True
      expected_retry -= 1
      if retry == 0:
        source_sha = parent
        break
      current = parent
    elif paths == [_RESULT]:
      if first or not saw_request:
        raise RemoteInvocationError("latest CMD attempt already has a result")
      _assert_committed_result(root, current)
      current = parent
    else:
      raise RemoteInvocationError("unauthorized CMD history mutation")
    first = False

  if _SHA.fullmatch(source_sha) is None:
    raise RemoteInvocationError("invalid source SHA")
  source_result = git(root, "cat-file", "-e", f"{source_sha}:{_RESULT}",
                      check=False)
  if source_result.returncode == 0:
    raise RemoteInvocationError("ordinary source branch contains CMD result")
  if source_sha != source_tip:
    present = git(root, "cat-file", "-e", source_tip + "^{commit}",
                  check=False)
    if present.returncode:
      git(root, "fetch", "--quiet", "--no-tags", "origin",
          f"refs/heads/{source_branch}")
    ancestor = git(
      root, "merge-base", "--is-ancestor", source_sha, source_tip,
      check=False,
    )
    if ancestor.returncode:
      raise RemoteInvocationError("CMD source revision is not on source branch")
  return _Request(
    branch, source_branch, source_sha, tip, latest_retry, target_argv,
  )


def _assert_hosted_grammar(source: Path, words: tuple[str, ...]) -> None:
  """Reuse the public parser; do not grant new remote command permissions."""
  if words[:2] == ("test", "results"):
    raise RemoteInvocationError("test results is read-only")
  probe = [*words, "--remote"]
  if len(probe) == 4 and probe[:2] == ["test", "RED"]:
    probe = [probe[0], probe[1], "--remote", probe[2]]
  try:
    parse_tokens(COMMANDS, Context(source, legal_only=False), probe)
    parse_tokens(COMMANDS, Context(source, legal_only=True), probe)
  except CommandGrammarError as exc:
    raise RemoteInvocationError("command is not eligible for hosted execution") from exc


class _StreamCapture(io.TextIOBase):
  def __init__(self, separate: io.StringIO, combined: io.StringIO):
    self._separate = separate
    self._combined = combined

  def write(self, value: str) -> int:
    self._separate.write(value)
    self._combined.write(value)
    return len(value)

  def flush(self) -> None:
    pass


def invoke_numbered(
  root: Path,
  argv: list[str],
  execute_local: Callable[[Path, list[str]], int],
  *,
  publish: Callable[[InvocationOutcome], None] | None = None,
) -> InvocationOutcome:
  """Validate first; invoke the normal CLI once in an isolated source checkout.

  The optional callback is the sole boundary for the #789 result publisher.
  This module neither commits nor publishes results.
  """
  request = _validate(root, argv)
  stdout = io.StringIO()
  stderr = io.StringIO()
  combined = io.StringIO()
  with tempfile.TemporaryDirectory(prefix="rwf-cmd-") as directory:
    source = Path(directory) / "source"
    git(root, "clone", "--quiet", "--no-hardlinks", str(root), str(source))
    git(source, "checkout", "--quiet", "-b",
        request.source_branch, request.source_sha)
    origin = _git(root, "remote", "get-url", "origin")
    git(source, "remote", "set-url", "origin", origin)
    _assert_hosted_grammar(source, request.argv)
    if _remote_tip(root, request.branch) != request.request_sha:
      raise RemoteInvocationError("CMD attempt was superseded before execution")
    with redirect_stdout(_StreamCapture(stdout, combined)):
      with redirect_stderr(_StreamCapture(stderr, combined)):
        try:
          status = execute_local(source, list(request.argv))
          if type(status) is not int:
            raise TypeError("local CLI returned a non-integer status")
        except Exception:
          traceback.print_exc()
          status = 1

  try:
    stdout.getvalue().encode("utf-8", errors="strict")
    stderr.getvalue().encode("utf-8", errors="strict")
  except UnicodeError as exc:
    raise RemoteInvocationError("command emitted non-UTF-8 output") from exc
  outcome = InvocationOutcome(
    request.branch, request.request_sha, request.source_sha,
    request.retry, status, stdout.getvalue(), stderr.getvalue(),
    combined.getvalue(),
  )
  if publish is not None:
    publish(outcome)
  return outcome
