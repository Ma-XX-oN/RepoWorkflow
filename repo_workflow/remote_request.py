"""Concurrent Git transport for numbered remote RWF requests.

The public CLI owns grammar and the status ticket owns retry permission.
This module only creates/reuses requests; it never executes commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from uuid import uuid4


class RemoteRequestError(RuntimeError):
  pass


@dataclass(frozen=True)
class SubmittedRequest:
  number: int
  branch: str
  source_sha: str
  request_sha: str
  reused: bool


_CMD = re.compile(r"CMD-([1-9][0-9]*)-(.+)\Z")
_SHA = re.compile(r"[0-9a-f]{40,64}\Z")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
  try:
    return subprocess.run(
      ["git", *args], cwd=root, capture_output=True, text=True,
      encoding="utf-8", errors="strict", check=False,
    )
  except OSError as exc:
    raise RemoteRequestError(f"cannot execute git: {exc}") from exc


def _git(root: Path, *args: str) -> str:
  result = _run(root, *args)
  if result.returncode:
    raise RemoteRequestError(
      f"git {args[0]} failed: {(result.stderr or result.stdout).strip()}"
    )
  return result.stdout.strip()


def _source(root: Path) -> tuple[str, str]:
  branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
  if _CMD.fullmatch(branch):
    raise RemoteRequestError("remote request cannot originate from a CMD branch")
  sha = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}")
  assert _SHA.fullmatch(sha)
  _git(root, "check-ref-format", "--branch", branch)
  if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != branch:
    raise RemoteRequestError("source branch changed during request")
  return branch, sha


def _remote_refs(root: Path, remote: str) -> dict[str, str]:
  refs = {}
  for line in _git(root, "ls-remote", "--heads", remote).splitlines():
    if "\t" not in line:
      raise RemoteRequestError("malformed remote ref listing")
    sha, ref = line.split("\t", 1)
    if not _SHA.fullmatch(sha) or not ref.startswith("refs/heads/"):
      raise RemoteRequestError("malformed remote ref listing")
    refs[ref.removeprefix("refs/heads/")] = sha
  return refs


def _inspect(root: Path, remote: str, branch: str, tip: str) -> bool:
  # Separate ref per invocation: concurrent fetches must not share FETCH_HEAD.
  ref = f"refs/rwf/cmd-inspect/{uuid4().hex}"
  try:
    result = _run(
      root, "fetch", "--no-tags", "--no-recurse-submodules",
      remote, f"refs/heads/{branch}:{ref}",
    )
    if result.returncode:
      raise RemoteRequestError("cannot inspect existing CMD")
    return _git(root, "rev-parse", f"{ref}^{{commit}}") == tip
  finally:
    _run(root, "update-ref", "-d", ref)


def _matches(
  root: Path, remote: str, branch: str, tip: str,
  source_sha: str, argv: list[str],
) -> bool | None:
  if not _inspect(root, remote, branch, tip):
    return None
  history = _git(root, "rev-list", "--reverse", f"{source_sha}..{tip}").splitlines()
  if not history:
    return False
  prior = source_sha
  count = 0
  for node in history:
    if _git(root, "rev-list", "--parents", "-n", "1", node) != f"{node} {prior}":
      return False
    prior = node
    paths = _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r", node
    ).splitlines()
    if paths == [".repoworkflow/result"]:
      if count == 0:
        return False
      continue
    if paths != [".ci/rwf"]:
      return False
    try:
      words = shlex.split(_git(root, "show", f"{node}:.ci/rwf"), posix=True)
    except ValueError:
      return False
    if words != [*argv, str(count)]:
      return False
    count += 1
  return count > 0


def _commit(root: Path, parent: str, text: str, *, source_sha: str) -> str:
  # A detached worktree keeps the source branch and user index untouched.
  with tempfile.TemporaryDirectory(prefix="rwf-cmd-") as directory:
    checkout = Path(directory) / "checkout"
    _git(root, "worktree", "add", "--quiet", "--detach", str(checkout), parent)
    try:
      request = checkout / ".ci" / "rwf"
      request.parent.mkdir(parents=True, exist_ok=True)
      request.write_text(text + "\n", encoding="utf-8", newline="\n")
      _git(checkout, "add", "-f", "--", ".ci/rwf")
      if _git(checkout, "diff", "--cached", "--name-only") != ".ci/rwf":
        raise RemoteRequestError("request must change only .ci/rwf")
      hooks = checkout / ".rwf-empty-hooks"
      hooks.mkdir()
      _git(
        checkout, "-c", "user.name=RepoWorkflow",
        "-c", "user.email=rwf@localhost",
        "-c", "commit.gpgsign=false",
        "-c", f"core.hooksPath={hooks}",
        "commit", "--quiet", "-m", "rwf: submit remote command",
        "-m", f"RWF-Source: {source_sha}",
      )
      sha = _git(checkout, "rev-parse", "HEAD")
      assert _SHA.fullmatch(sha)
      changed = _git(
        checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", sha,
      ).splitlines()
      if changed != [".ci/rwf"]:
        raise RemoteRequestError("CMD commit changed non-request paths")
      return sha
    finally:
      _git(root, "worktree", "remove", "--force", str(checkout))


def _argv(argv: list[str]) -> None:
  if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
    raise RemoteRequestError("request argv must be a list of strings")
  if not argv or argv[-1] != "--remote" or argv.count("--remote") != 1:
    raise RemoteRequestError("expected one terminal public --remote")
  if "--poll" in argv or any("\0" in token for token in argv):
    raise RemoteRequestError("poll or NUL is not valid request argv")


def _remote_name(remote: str) -> None:
  if not isinstance(remote, str) or not re.fullmatch(
    r"[A-Za-z0-9._/-]+", remote
  ) or remote.startswith("-"):
    raise RemoteRequestError("invalid Git remote name")


def submit_request(
  root: Path, argv: list[str], *, remote: str = "origin",
  max_collisions: int = 100,
) -> SubmittedRequest:
  """Submit or reuse identical source revision and argument vector."""
  _argv(argv)
  _remote_name(remote)
  root = Path(root)
  source_branch, source_sha = _source(root)
  payload = shlex.join([*argv, "0"])
  assert shlex.split(payload, posix=True) == [*argv, "0"]
  commit = None
  for _ in range(max_collisions):
    refs = _remote_refs(root, remote)
    numbers = []
    stale = False
    for branch, tip in refs.items():
      match = _CMD.fullmatch(branch)
      if match is None:
        continue
      numbers.append(int(match.group(1)))
      if match.group(2) != source_branch:
        continue
      matched = _matches(root, remote, branch, tip, source_sha, argv)
      if matched is None:
        stale = True
        break
      if matched:
        if _source(root) != (source_branch, source_sha):
          raise RemoteRequestError("source changed while reusing CMD")
        # Do not return an obsolete request SHA after a concurrent retry.
        if _remote_refs(root, remote).get(branch) != tip:
          stale = True
          break
        return SubmittedRequest(
          int(match.group(1)), branch, source_sha, tip, True,
        )
    if stale:
      continue
    if _source(root) != (source_branch, source_sha):
      raise RemoteRequestError("source tip changed during CMD allocation")
    number = max(numbers, default=0) + 1
    branch = f"CMD-{number}-{source_branch}"
    if commit is None:
      commit = _commit(root, source_sha, payload, source_sha=source_sha)
    if _source(root) != (source_branch, source_sha):
      raise RemoteRequestError("source changed during request preparation")
    result = _run(
      root, "push", "--porcelain",
      f"--force-with-lease=refs/heads/{branch}:",
      remote, f"{commit}:refs/heads/{branch}",
    )
    if result.returncode == 0:
      return SubmittedRequest(
        number, branch, source_sha, commit,
        "[up to date]" in result.stdout,
      )
    # Only a genuine concurrent branch collision warrants retrying.
    if branch not in _remote_refs(root, remote):
      raise RemoteRequestError("CMD publication rejected: " + result.stderr.strip())
  raise RemoteRequestError("CMD allocation did not converge")


def retry_request(
  root: Path, branch: str, expected_tip: str, argv: list[str], *,
  permitted: bool, remote: str = "origin",
) -> SubmittedRequest:
  """Advance the existing CMD only after the status owner proves it safe."""
  if not permitted:
    raise RemoteRequestError("retry requires prior-attempt suppression evidence")
  _argv(argv)
  _remote_name(remote)
  match = _CMD.fullmatch(branch)
  if match is None or not _SHA.fullmatch(expected_tip):
    raise RemoteRequestError("invalid CMD retry identity")
  root = Path(root)
  if _remote_refs(root, remote).get(branch) != expected_tip:
    raise RemoteRequestError("stale CMD retry tip")
  if not _inspect(root, remote, branch, expected_tip):
    raise RemoteRequestError("CMD changed during inspection")
  markers = _git(
    root, "log", "--reverse", "--format=%H", "--fixed-strings",
    "--grep=RWF-Source:", expected_tip,
  ).splitlines()
  first = None
  source_sha = None
  for node in markers:
    message = _git(root, "log", "-1", "--format=%B", node)
    match_source = re.search(r"^RWF-Source: ([0-9a-f]{40,64})$", message, re.M)
    if match_source is None:
      continue
    if _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r", node
    ) != ".ci/rwf":
      continue
    try:
      marker_argv = shlex.split(_git(root, "show", f"{node}:.ci/rwf"))
    except ValueError:
      continue
    if marker_argv != [*argv, "0"]:
      continue
    first = node
    source_sha = match_source.group(1)
    break
  if first is None or source_sha is None:
    raise RemoteRequestError("missing CMD source identity")
  if _git(root, "rev-parse", f"{first}^") != source_sha:
    raise RemoteRequestError("CMD source identity does not match parent")
  if not _matches(root, remote, branch, expected_tip, source_sha, argv):
    raise RemoteRequestError("invalid CMD retry lineage")
  prior = shlex.split(_git(root, "show", f"{expected_tip}:.ci/rwf"), posix=True)
  if len(prior) != len(argv) + 1 or prior[:-1] != argv:
    raise RemoteRequestError("retry command mismatch")
  count = int(prior[-1])
  commit = _commit(
    root, expected_tip, shlex.join([*argv, str(count + 1)]),
    source_sha=source_sha,
  )
  result = _run(root, "push", "--porcelain", remote, f"{commit}:refs/heads/{branch}")
  if result.returncode:
    raise RemoteRequestError("CMD retry publication rejected: " + result.stderr.strip())
  return SubmittedRequest(int(match.group(1)), branch, source_sha, commit, False)


def submit_unpolled(root: Path, argv: list[str], *, remote: str = "origin") -> int:
  """Return 0 for submission/reuse, 1 for invalid submission, not command status."""
  try:
    result = submit_request(root, argv, remote=remote)
  except (RemoteRequestError, OSError, UnicodeError) as exc:
    import sys
    print(f"RepoWorkflow remote submission error: {exc}", file=sys.stderr)
    return 1
  print(f"CMD#{result.number} {result.branch}")
  return 0
