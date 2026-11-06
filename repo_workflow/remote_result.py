"""Atomic CMD-only publication and readback of numbered invocation outcomes.

The central invocation wrapper validates a request before handing the completed
InvocationOutcome to this module. No provider API or client polling lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
  from .remote_invocation import InvocationOutcome


_RESULT = ".repoworkflow/result"
_MARKER = ".ci/rwf"
_CMD = re.compile(r"CMD-[1-9][0-9]*-.+\Z")
_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_STATUS = re.compile(r"-?[0-9]+\Z")


class RemoteResultError(RuntimeError):
  """Invalid, stale or conflicting CMD publication or readback."""


@dataclass(frozen=True)
class PublishedResult:
  branch: str
  request_sha: str
  retry: int
  exit_code: int
  output: str
  publication_sha: str


def _run(root: Path, *args: str, data: bytes | None = None,
         env: dict[str, str] | None = None) -> bytes:
  try:
    result = subprocess.run(
      ["git", *args], cwd=root, input=data, capture_output=True,
      check=False, env=env,
    )
  except OSError as exc:
    raise RemoteResultError(f"Git invocation failed: {exc}") from exc
  if result.returncode:
    raise RemoteResultError(
      f"Git {args[0]} failed: " +
      result.stderr.decode("utf-8", errors="replace").strip()
    )
  return result.stdout


def _text(root: Path, *args: str) -> str:
  try:
    return _run(root, *args).decode("utf-8", errors="strict").strip()
  except UnicodeError as exc:
    raise RemoteResultError("Git metadata must be UTF-8") from exc


def _remote_tip(root: Path, branch: str, remote: str) -> str:
  if not _CMD.fullmatch(branch):
    raise RemoteResultError("result publication requires a numbered CMD branch")
  if not re.fullmatch(r"[A-Za-z0-9._/-]+", remote) or remote.startswith("-"):
    raise RemoteResultError("invalid Git remote")
  lines = _text(root, "ls-remote", "--heads", remote,
                f"refs/heads/{branch}").splitlines()
  if len(lines) != 1:
    raise RemoteResultError("CMD branch is absent or ambiguous")
  parts = lines[0].split()
  if len(parts) != 2 or parts[1] != f"refs/heads/{branch}" or not _SHA.fullmatch(parts[0]):
    raise RemoteResultError("invalid CMD reference advertisement")
  return parts[0]


def _fetch(root: Path, branch: str, remote: str, expected: str) -> tuple[str, str]:
  ref = f"refs/rwf/result-inspect/{uuid4().hex}"
  _run(root, "fetch", "--no-tags", "--no-recurse-submodules", remote,
       f"refs/heads/{branch}:{ref}")
  actual = _text(root, "rev-parse", f"{ref}^{{commit}}")
  if actual != expected:
    _run(root, "update-ref", "-d", ref)
    raise RemoteResultError("CMD branch advanced during result inspection")
  return ref, actual


def _request(root: Path, tip: str) -> tuple[str, int]:
  marker = _text(root, "log", "-1", "--format=%H", tip, "--", _MARKER)
  if not _SHA.fullmatch(marker):
    raise RemoteResultError("CMD request marker is missing")
  import shlex
  try:
    words = shlex.split(_run(root, "show", f"{marker}:{_MARKER}").decode(
      "utf-8", errors="strict"), posix=True)
  except (UnicodeError, ValueError) as exc:
    raise RemoteResultError("invalid CMD request marker") from exc
  if len(words) < 3 or words[-2] != "--remote" or not re.fullmatch(r"0|[1-9][0-9]*", words[-1]):
    raise RemoteResultError("CMD request is not numbered")
  return marker, int(words[-1])


def _result_at(root: Path, commit: str) -> tuple[int, str]:
  try:
    raw = _run(root, "show", f"{commit}:{_RESULT}").decode("utf-8", "strict")
  except UnicodeError as exc:
    raise RemoteResultError("result is not valid UTF-8") from exc
  status, separator, output = raw.partition("\n")
  if not separator or not _STATUS.fullmatch(status) or str(int(status)) != status:
    raise RemoteResultError("result has invalid decimal exit status")
  return int(status), output


def read_result(root: Path, branch: str, *, remote: str = "origin") -> PublishedResult | None:
  """Return completed latest attempt or None for a request still pending.

  A result belonging to an older retry is never treated as current.
  """
  root = Path(root)
  tip = _remote_tip(root, branch, remote)
  ref, _ = _fetch(root, branch, remote, tip)
  try:
    request_sha, retry = _request(root, tip)
    if tip == request_sha:
      return None
    parents = _text(root, "rev-list", "--parents", "-n", "1", tip).split()
    paths = _text(root, "diff-tree", "--no-commit-id", "--name-only",
                  "-r", tip).splitlines()
    if len(parents) != 2 or parents[1] != request_sha or paths != [_RESULT]:
      raise RemoteResultError("CMD tip has an invalid publication lineage")
    message = _text(root, "show", "-s", "--format=%B", tip)
    if (message.count(f"RWF-Request: {request_sha}") != 1 or
        message.count(f"RWF-Retry: {retry}") != 1 or
        not re.search(rf"(?m)^RWF-Request: {re.escape(request_sha)}$", message) or
        not re.search(rf"(?m)^RWF-Retry: {retry}$", message)):
      raise RemoteResultError("result identity does not match request")
    status, output = _result_at(root, tip)
    return PublishedResult(branch, request_sha, retry, status, output, tip)
  finally:
    _run(root, "update-ref", "-d", ref)


def publish_result(root: Path, outcome: InvocationOutcome, *,
                   remote: str = "origin") -> PublishedResult:
  """CAS-publish exactly one terminal result onto its current CMD request.

  A stale retry, duplicate completion or competing publisher fails closed.
  No ordinary branch or local index/worktree is modified.
  """
  root = Path(root)
  if (type(outcome.exit_code) is not int or type(outcome.retry) is not int or
      outcome.retry < 0 or not _SHA.fullmatch(outcome.request_sha) or
      not _SHA.fullmatch(outcome.source_sha) or
      not isinstance(outcome.output, str)):
    raise RemoteResultError("invalid invocation result identity")
  data = (str(outcome.exit_code) + "\n" + outcome.output).encode(
    "utf-8", errors="strict")
  tip = _remote_tip(root, outcome.branch, remote)
  if tip != outcome.request_sha:
    raise RemoteResultError("request is stale, superseded or already published")
  ref, _ = _fetch(root, outcome.branch, remote, tip)
  try:
    marker, retry = _request(root, tip)
    if marker != outcome.request_sha or retry != outcome.retry:
      raise RemoteResultError("attempt identity differs from CMD marker")
    source = _text(root, "show", "-s", "--format=%B", marker)
    if not re.search(rf"(?m)^RWF-Source: {re.escape(outcome.source_sha)}$", source):
      raise RemoteResultError("CMD source identity does not match outcome")
    changed = _text(root, "diff-tree", "--no-commit-id", "--name-only", "-r", marker).splitlines()
    if changed != [_MARKER]:
      raise RemoteResultError("CMD request modified non-marker paths")
    # A temporary alternate index generates one tree, independently of any
    # caller's staged files. Publication becomes visible in a single Git ref update.
    with tempfile.TemporaryDirectory(prefix="rwf-result-") as directory:
      index = str(Path(directory) / "index")
      env = dict(os.environ, GIT_INDEX_FILE=index)
      blob = _run(root, "hash-object", "-w", "--stdin", data=data).decode().strip()
      previous = _text(root, "ls-tree", tip, "--", _RESULT)
      # Retried attempts can return byte-identical output. A new result
      # commit must still change this path for the accepted CMD lineage
      # validators to recognize it; toggle the Git file mode in that case.
      mode = "100644"
      if previous:
        fields = previous.split()
        if len(fields) == 4 and fields[1] == "blob" and fields[2] == blob:
          mode = "100755" if fields[0] == "100644" else "100644"
      _run(root, "read-tree", f"{tip}^{{tree}}", env=env)
      _run(root, "update-index", "--add", "--cacheinfo",
           mode, blob, _RESULT, env=env)
      tree = _run(root, "write-tree", env=env).decode().strip()
    identity_env = dict(os.environ, GIT_AUTHOR_NAME="RepoWorkflow",
                        GIT_AUTHOR_EMAIL="rwf@localhost",
                        GIT_COMMITTER_NAME="RepoWorkflow",
                        GIT_COMMITTER_EMAIL="rwf@localhost")
    message = ("rwf: publish remote result\n\n"
               f"RWF-Request: {marker}\nRWF-Retry: {retry}\n")
    commit = _run(root, "commit-tree", tree, "-p", tip,
                  data=message.encode("utf-8"), env=identity_env).decode().strip()
    # Compare-and-swap the authoritative remote ref, never force over another attempt.
    _run(root, "push", "--porcelain",
         f"--force-with-lease=refs/heads/{outcome.branch}:{tip}",
         remote, f"{commit}:refs/heads/{outcome.branch}")
    if _remote_tip(root, outcome.branch, remote) != commit:
      raise RemoteResultError("published CMD result is no longer authoritative")
    return PublishedResult(outcome.branch, marker, retry,
                           outcome.exit_code, outcome.output, commit)
  finally:
    _run(root, "update-ref", "-d", ref)
