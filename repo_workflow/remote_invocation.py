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
import sys
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


def _lf_records(raw: str) -> list[str]:
  """Separate only Git's physical LF records, never Unicode line characters."""
  if not raw:
    return []
  if not raw.endswith("\n"):
    raise RemoteInvocationError("unterminated Git ref advertisement")
  return raw[:-1].split("\n")


def _origin_url(root: Path) -> str:
  """Preserve the exact URL rather than stripping valid trailing characters."""
  raw = git(root, "remote", "get-url", "origin").stdout
  if (not raw.endswith("\n") or len(raw) == 1
      or "\n" in raw[:-1] or "\x00" in raw):
    raise RemoteInvocationError("invalid Git origin URL record")
  return raw[:-1]


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


def _request_source(root: Path, commit: str) -> str:
  message = _git(root, "show", "-s", "--format=%B", commit)
  trailers = re.findall(r"(?m)^RWF-Source: ([0-9a-f]{40})$", message)
  if len(trailers) != 1:
    raise RemoteInvocationError("missing or malformed CMD source identity trailer")
  return trailers[0]


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
  status, separator, _ = raw.partition("\n")
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
  records = _lf_records(completed.stdout)
  if len(records) != 1:
    raise RemoteInvocationError(f"remote branch missing or ambiguous: {branch}")
  sha, sep, ref = records[0].partition("\t")
  if not sep or ref != f"refs/heads/{branch}":
    raise RemoteInvocationError("invalid authoritative branch advertisement")
  if _SHA.fullmatch(sha) is None:
    raise RemoteInvocationError("invalid advertised Git revision")
  return sha


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
  source_trailers: list[str] = []
  while True:
    parent, paths = _parent_and_paths(root, current)
    if paths == [_MARKER]:
      local_argv, retry = _committed_marker(root, current)
      source_trailers.append(_request_source(root, current))
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
  if any(trailer != source_sha for trailer in source_trailers):
    raise RemoteInvocationError("CMD source identity trailer mismatches source tip")
  source_result = git(root, "cat-file", "-e", f"{source_sha}:{_RESULT}",
                      check=False)
  if source_result.returncode == 0:
    raise RemoteInvocationError("ordinary source branch contains CMD result")
  if source_sha != source_tip:
    raise RemoteInvocationError("CMD source branch advanced since submission")
  return _Request(
    branch, source_branch, source_sha, tip, latest_retry, target_argv,
  )


def _assert_hosted_grammar(source: Path, words: tuple[str, ...]) -> None:
  """Reuse the public parser; do not grant new remote command permissions."""
  if words[:2] == ("test", "results"):
    raise RemoteInvocationError("test results is read-only")
  try:
    parse_tokens(COMMANDS, Context(source, legal_only=False), list(words))
    parse_tokens(COMMANDS, Context(source, legal_only=True), list(words))
  except CommandGrammarError as exc:
    raise RemoteInvocationError("command is not eligible for hosted execution") from exc



def _local_branches(root: Path) -> dict[str, str]:
  """Snapshot refs belonging to the command's isolated source repository."""
  refs: dict[str, str] = {}
  for line in _lf_records(git(
    root, "for-each-ref", "--format=%(refname:short) %(objectname)",
    "refs/heads",
  ).stdout):
    branch, separator, sha = line.rpartition(" ")
    if not separator or not branch or _SHA.fullmatch(sha) is None:
      raise RemoteInvocationError("invalid local branch advertisement")
    if branch in refs:
      raise RemoteInvocationError("duplicate local branch identity")
    refs[branch] = sha
  return refs



def _local_tags(root: Path) -> dict[str, str]:
  """Snapshot exact tag-object IDs, not peeled commit targets."""
  refs: dict[str, str] = {}
  for line in _lf_records(git(
    root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/tags",
  ).stdout):
    ref, separator, sha = line.rpartition(" ")
    if (not separator or not ref.startswith("refs/tags/")
        or not ref[len("refs/tags/"):] or _SHA.fullmatch(sha) is None
        or ref in refs):
      raise RemoteInvocationError("invalid local Git tag advertisement")
    refs[ref] = sha
  return refs


def _remote_tag_oid(root: Path, ref: str) -> str | None:
  advertised = git(root, "ls-remote", "--tags", "origin", ref, check=False)
  if advertised.returncode:
    raise RemoteInvocationError("cannot verify authoritative remote tag")
  matches = []
  for line in _lf_records(advertised.stdout):
    sha, sep, advertised_ref = line.partition("\t")
    if not sep or not advertised_ref.startswith("refs/tags/"):
      raise RemoteInvocationError("invalid remote tag advertisement")
    if advertised_ref == ref:
      if _SHA.fullmatch(sha) is None:
        raise RemoteInvocationError("invalid advertised tag object")
      matches.append(sha)
  if len(matches) > 1:
    raise RemoteInvocationError("ambiguous authoritative tag")
  return matches[0] if matches else None


def _publish_command_branches(
  root: Path, request: _Request, before: dict[str, str],
  before_tags: dict[str, str],
) -> None:
  """Push only refs the normal command committed; never stage command files."""
  # A command that changed tracked files without committing them has not
  # produced durable state and must not be reported as completed successfully.
  dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
  if dirty:
    raise RemoteInvocationError(
      "command left uncommitted repository changes: " + dirty[:400]
    )
  after = _local_branches(root)
  changes = []
  for branch, revision in after.items():
    old = before.get(branch)
    if old == revision:
      continue
    if _CMD.fullmatch(branch):
      raise RemoteInvocationError("normal command modified CMD branch identity")
    base = old or request.source_sha
    if git(root, "merge-base", "--is-ancestor", base, revision,
           check=False).returncode:
      raise RemoteInvocationError("command rewrote branch history: " + branch)
    current = git(root, "ls-remote", "--heads", "origin",
                  f"refs/heads/{branch}", check=False)
    if current.returncode:
      raise RemoteInvocationError("cannot check command destination: " + branch)
    remote_sha = current.stdout.split()[0] if current.stdout.strip() else None
    if remote_sha == revision:
      # An existing command may have published the exact result already.
      continue
    if remote_sha != old:
      raise RemoteInvocationError("command destination advanced: " + branch)
    changes.append((branch, revision, old))
  after_tags = _local_tags(root)
  if set(before_tags) - set(after_tags):
    raise RemoteInvocationError("command deleted an existing Git tag")
  tag_changes: list[tuple[str, str]] = []
  for ref, revision in after_tags.items():
    old = before_tags.get(ref)
    if old is not None:
      if old != revision:
        raise RemoteInvocationError("command rewrote an existing Git tag")
      continue
    published = _remote_tag_oid(root, ref)
    if published == revision:
      continue
    if published is not None:
      raise RemoteInvocationError("authoritative Git tag already exists: " + ref)
    tag_changes.append((ref, revision))
  if not changes and not tag_changes:
    return
  command = ["push", "--porcelain", "--atomic"]
  for branch, _, old in changes:
    command.append(f"--force-with-lease=refs/heads/{branch}:{old or ''}")
  for ref, _ in tag_changes:
    command.append(f"--force-with-lease={ref}:")
  command.append("origin")
  command.extend(
    f"{revision}:refs/heads/{branch}" for branch, revision, _ in changes
  )
  command.extend(f"{revision}:{ref}" for ref, revision in tag_changes)
  published = git(root, *command, check=False)
  if published.returncode:
    # With --porcelain, Git reports per-ref rejection reasons on stdout.
    # Preserve both protocol streams; stderr alone loses the actual cause.
    detail = "\n".join(
      value for value in (published.stdout.strip(), published.stderr.strip())
      if value
    )
    raise RemoteInvocationError(
      "command branch publication failed: " + detail
    )
  for branch, revision, _ in changes:
    if _remote_tip(root, branch) != revision:
      raise RemoteInvocationError("command branch readback mismatch: " + branch)
  for ref, revision in tag_changes:
    if _remote_tag_oid(root, ref) != revision:
      raise RemoteInvocationError("command tag readback mismatch: " + ref)


def emit_outcome(outcome: InvocationOutcome) -> None:
  """Emit strict UTF-8 bytes even when the host text codec differs."""
  for stream, value in (
    (sys.stdout, outcome.stdout),
    (sys.stderr, outcome.stderr),
  ):
    encoded = value.encode("utf-8", errors="strict")
    binary = getattr(stream, "buffer", None)
    if binary is None:
      stream.write(value)
    else:
      binary.write(encoded)
      binary.flush()


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
  execute_local: Callable[
    [Path, list[str]], int | subprocess.CompletedProcess[bytes]
  ],
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
    origin = _origin_url(root)
    git(source, "remote", "set-url", "origin", origin)
    try:
      _assert_hosted_grammar(source, request.argv)
    except RemoteInvocationError as exc:
      # The CMD identity is authenticated, so a rejected command still gets
      # a durable terminal result. Never invoke the invalid command handler.
      diagnostic = str(exc) + "\n"
      outcome = InvocationOutcome(
        request.branch, request.request_sha, request.source_sha,
        request.retry, 2, "", diagnostic, diagnostic,
      )
      if publish is not None:
        publish(outcome)
      return outcome
    before_branches = _local_branches(source)
    before_tags = _local_tags(source)
    if _remote_tip(root, request.branch) != request.request_sha:
      raise RemoteInvocationError("CMD attempt was superseded before execution")
    with redirect_stdout(_StreamCapture(stdout, combined)):
      with redirect_stderr(_StreamCapture(stderr, combined)):
        try:
          result = execute_local(source, list(request.argv))
          if isinstance(result, subprocess.CompletedProcess):
            if not isinstance(result.stdout, bytes):
              raise TypeError("captured stdout must be bytes")
            if not isinstance(result.stderr, bytes):
              raise TypeError("captured stderr must be bytes")
            standard = result.stdout.decode("utf-8", errors="strict")
            errors = result.stderr.decode("utf-8", errors="strict")
            stdout.write(standard)
            stderr.write(errors)
            combined.write(standard + errors)
            status = result.returncode
          else:
            status = result
          if type(status) is not int:
            raise TypeError("local CLI returned a non-integer status")
          _publish_command_branches(source, request, before_branches, before_tags)
        except UnicodeError as exc:
          raise RemoteInvocationError("command emitted non-UTF-8 output") from exc
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
