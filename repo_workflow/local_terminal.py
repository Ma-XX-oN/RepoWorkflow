"""Local evidence-bound terminal publication and safe consumer retry."""
from __future__ import annotations
import json
from pathlib import Path
import re
from .config import load_config
from .git import current_branch
from .local import verify_local
from typing import Callable
from .retry_evidence import isolate_retry_evidence
from .terminal_tag import publish_terminal_tag, TerminalTagError

def verify_consumer_retry(
  root: Path, engine_root: Path, prepared: list[tuple[str, str]],
  verifier: Callable = verify_local,
) -> str:
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TerminalTagError("consumer regression requires an issue branch")
  with isolate_retry_evidence(root, int(match.group(1))):
    return verifier(
      root, engine_root=engine_root, push=False, tag_result=False,
      candidate_observer=lambda sha, version: prepared.append((sha, version)),
    )

def publish_local_terminal(root: Path, *, stage: str) -> str | None:
  if stage not in {"regression", "integration"}:
    raise TerminalTagError("unsupported local terminal stage")
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TerminalTagError("terminal log requires issue branch")
  log = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  try:
    # JSONL records are delimited only by physical LF, not Unicode U+2028/U+2029.
    record = json.loads(log.read_text(encoding="utf-8").removesuffix("\n").rsplit("\n", 1)[-1])
  except (OSError, ValueError, IndexError) as error:
    raise TerminalTagError("latest local terminal evidence unavailable") from error
  if not isinstance(record, dict) or record.get("kind") != stage:
    raise TerminalTagError("latest local observation is not the terminal stage")
  status = record.get("result")
  if status == "incomplete":
    return None
  if status not in {"succeeded", "failed"}:
    raise TerminalTagError("local terminal outcome is not definitive")
  if record.get("headChangedDuringTest") is not False:
    return None  # Nonreusable observation never creates a terminal tag.
  if record.get("uncommittedChanges") != []:
    return None  # Preserve dirty-source evidence without promoting it.
  version = record.get("testVersion")
  if not isinstance(version, str):
    if not (root / "VERSION").is_file():
      return None  # Unversioned synthetic engine fixture; no tag.
    raise TerminalTagError("no authoritative local development version")
  remote = (
    load_config(root)["repository"]["authoritativeRemote"]
    if (root / ".ci/repoworkflow.json").is_file() else "origin"
  )
  return publish_terminal_tag(
    root, stage=stage, remote=remote, version=version,
    candidate=record["testSHA"],
    outcome="PASS" if status == "succeeded" else "FAIL",
    canonical_log=log, push=False,
  )
