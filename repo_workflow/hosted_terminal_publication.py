"""Publish an immutable hosted terminal tag only after canonical remote evidence."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

from .hosted_terminal_binding import bind_hosted_terminal, HostedTerminalError
from .terminal_tag import publish_terminal_tag, TerminalTagError


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )
  if result.returncode:
    raise HostedTerminalError("cannot verify hosted remote publication")
  return result.stdout.strip()


def publish_hosted_terminal(
  root: Path, *, branch: str, stage: str,
  invocation: str, candidate: str, run_id: int,
  remote: str = "origin",
) -> str | None:
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
  if match is None:
    raise HostedTerminalError("hosted terminal requires issue branch")
  relative = f".repoworkflow/validation/testResults-{match.group(1)}.jsonl"
  path = root / relative
  binding = bind_hosted_terminal(
    root, stage=stage, candidate=candidate, invocation=invocation,
    run_id=run_id, canonical_log=path,
  )
  if binding is None:
    return None
  head = _git(root, "rev-parse", "HEAD")
  refs = _git(root, "ls-remote", remote, "refs/heads/" + branch).split()
  if len(refs) != 2 or refs[0] != head:
    raise HostedTerminalError("hosted canonical publication branch is stale")
  if _git(root, "rev-parse", "HEAD^") != invocation:
    raise HostedTerminalError("hosted result publication parent mismatch")
  changes = _git(
    root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD",
  ).splitlines()
  if changes != [relative]:
    raise HostedTerminalError("hosted result commit modified source inputs")
  if _git(root, "show", "-s", "--format=%s", "HEAD") != (
    "test: publish hosted evidence from run " + str(run_id)
  ):
    raise HostedTerminalError("hosted result commit lacks provider publication identity")
  committed_log = _git(root, "show", "HEAD:" + relative)
  try:
    actual_log = path.read_text(encoding="utf-8").rstrip("\n")
  except OSError as error:
    raise HostedTerminalError("hosted canonical log is absent") from error
  if committed_log != actual_log:
    raise HostedTerminalError("hosted log differs from published commit")
  try:
    return publish_terminal_tag(
      root, remote=remote, canonical_log=path, push=True, **binding,
    )
  except TerminalTagError as error:
    raise HostedTerminalError("immutable hosted terminal tag rejected") from error
