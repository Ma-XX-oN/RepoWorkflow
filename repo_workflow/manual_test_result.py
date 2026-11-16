"""Exact-source manual integration results and fail-closed failure handoff.

All evidence is appended to existing per-issue testResults JSONL authority.
A private recovery journal blocks completion across interrupted writes/steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Literal

from .manual_test_state import (
  ManualSelection, ManualSelectionError, read_active_manual_selection,
  select_manual_case, _active, _atomic, _cases, _guard, _issue,
  _paths, _read, _validate_current,
)


class ManualResultError(ManualSelectionError):
  """No verified completion is available; repair or reconciliation required."""


@dataclass(frozen=True)
class ManualOutcome:
  case: str
  candidate_sha: str
  result: str
  evidence_id: str
  evidence_path: str
  completed: bool


@dataclass(frozen=True)
class FailureHandoff:
  lifecycle: str
  version_before: str
  version_after: str
  repair_owner: str


def _verified_handoff(value: object) -> None:
  if not isinstance(value, FailureHandoff):
    raise ManualResultError("manual FAIL has no verified repair handoff")
  before = _version_components(value.version_before)
  after = _version_components(value.version_after)
  if (value.lifecycle != "active"
      or before is None or after != before or value.version_after != value.version_before
      or not isinstance(value.repair_owner, str) or not value.repair_owner.strip()):
    raise ManualResultError("manual FAIL handoff contract rejected")


def _evidence_path(root: Path, issue: int) -> Path:
  return (Path(root).resolve() / ".repoworkflow" / "validation"
          / f"testResults-{_issue(issue)}.jsonl")


def _events(path: Path) -> list[dict]:
  if path.is_symlink():
    raise ManualResultError("canonical test results path is a symlink")
  if not path.exists():
    return []
  try:
    from .test_results_reader import parse_testing_log
    records = parse_testing_log(path.read_text(encoding="utf-8"))
  except (OSError, UnicodeError, ValueError) as error:
    raise ManualResultError("canonical test results readback UNKNOWN") from error
  for entry in records:
    if entry.get("kind") != "manual-integration":
      continue
    if (entry.get("result") not in {"succeeded", "failed"}
        or not isinstance(entry.get("manualCase"), str)
        or not isinstance(entry.get("definitionDigest"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["definitionDigest"])
        or not isinstance(entry.get("manualEvidenceId"), str)
        or not isinstance(entry.get("operator"), str)
        or not entry["operator"]
        or not isinstance(entry.get("evidenceRef"), str)
        or not entry["evidenceRef"]):
      raise ManualResultError("invalid canonical manual test evidence")
  return records


def _matching_event(path: Path, event: dict) -> bool:
  matching = [record for record in _events(path)
              if record.get("manualEvidenceId") == event["manualEvidenceId"]]
  if len(matching) > 1:
    raise ManualResultError("duplicate canonical manual evidence ID")
  if matching and matching[0] != event:
    raise ManualResultError("canonical manual evidence readback differs")
  return bool(matching)


def _failed_candidate(path: Path, candidate_sha: str) -> bool:
  return any(entry.get("kind") == "manual-integration"
             and entry.get("testSHA") == candidate_sha
             and entry.get("result") == "failed" for entry in _events(path))


def _append(path: Path, record: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  if path.is_symlink():
    raise ManualResultError("canonical test results path is a symlink")
  line = json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
  with path.open("a", encoding="utf-8") as output:
    output.write(line)
    output.flush()
    os.fsync(output.fileno())


def _consume(selection_path: Path) -> None:
  _atomic(selection_path, {"schema": 1, "active": []})
  if _read(selection_path) != {"schema": 1, "active": []}:
    raise ManualResultError("manual consumption readback UNKNOWN")


def _clear_pending(path: Path) -> None:
  path.unlink()
  if path.exists() or path.is_symlink():
    raise ManualResultError("manual journal removal readback UNKNOWN")


def _version_components(value: str) -> tuple[int, int] | None:
  match = re.fullmatch(r"\d+\.\d+\.\d+-issue\.\d+\.(\d+)\.(\d+)", value)
  return (int(match.group(1)), int(match.group(2))) if match else None


def apply_manual_failure(root: Path, issue: int, candidate_sha: str):
  """Record the canonical lifecycle handoff without changing the version.

  Failure preserves Q and R. Preparing a repaired implementation advances Q
  and resets R to zero; only reintegration against a newer parent advances R.
  """
  from .lifecycle_store import LifecycleStore
  from .state_store import WriterIdentity
  from .version_adapter import read_development_version
  from .config import load_config

  writer_id, session_id = os.environ.get("RWF_WRITER_ID"), os.environ.get("RWF_SESSION_ID")
  if not writer_id or not session_id:
    raise ManualResultError("failure handoff requires RWF_WRITER_ID and RWF_SESSION_ID")
  store = LifecycleStore(root)
  snapshot = store.read(issue)
  state = snapshot.lifecycle.state
  if state in {"in_review", "accepted"}:
    store.transition(
      issue, "reject/reopen", snapshot.revision,
    )
  elif state != "active":
    raise ManualResultError("manual FAIL cannot reopen lifecycle state " + state)
  observed = store.read(issue).lifecycle
  if observed.state != "active":
    raise ManualResultError("manual FAIL lifecycle rejection readback UNKNOWN")
  if (root / ".ci/repoworkflow.json").is_file():
    version = read_development_version(root, load_config(root))
  else:
    from .engine_version_adapter import read_engine_version
    version = read_engine_version(root)
  log = _evidence_path(root, issue)
  failures = [row for row in _events(log) if row.get("kind") == "manual-integration"
    and row.get("testSHA") == candidate_sha and row.get("result") == "failed"]
  if not failures:
    raise ManualResultError("manual FAIL has no recorded test observation")
  from .git import current_branch
  from .terminal_tag import publish_terminal_tag
  _validate_current(root, candidate_sha)
  summary = {"kind": "integration", "runner": "manual",
    "result": "failed", "testSHA": candidate_sha, "testVersion": version,
    "headChangedDuringTest": False, "uncommittedChanges": [],
    "branch": current_branch(root),
    "sourceManualEvidenceId": failures[-1]["manualEvidenceId"]}
  with log.open("a", encoding="utf-8", newline="\n") as handle:
    handle.write(json.dumps(summary, sort_keys=True) + "\n")
  publish_terminal_tag(root, stage="integration", remote="origin", version=version,
    candidate=candidate_sha, outcome="FAIL", canonical_log=log, push=False)
  return FailureHandoff(observed.state, version, version,
                        writer_id)


def record_manual_result(
  root: Path, issue: int, candidate_sha: str,
  result: Literal["succeeded", "failed"], *,
  operator: str | None = None, evidence_ref: str | None = None, cases=None,
  on_failure: Callable[[Path, int, str], object] | None = None,
) -> ManualOutcome:
  """Write once, read back and consume exactly one active case.

  On a failure, result evidence precedes lifecycle/version mutation. Any
  interrupted or rejected handoff leaves a durable blocking journal.
  """
  if result not in ("succeeded", "failed"):
    raise ManualResultError("invalid manual result (TIMEOUT must be deferred)")
  if operator is None:
    operator = os.environ.get("RWF_WRITER_ID")
  if not isinstance(operator, str) or not operator.strip():
    raise ManualResultError("manual operator identity is required")
  if evidence_ref is not None and (not isinstance(evidence_ref, str)
                                   or not evidence_ref.strip()):
    raise ManualResultError("invalid manual evidence reference")
  _validate_current(root, candidate_sha)
  selection, pending, lock = _paths(root, issue)
  log = _evidence_path(root, issue)
  with _guard(lock):
    current = _active(root, issue, candidate_sha, cases)
    if current is None:
      raise ManualResultError("exactly one active manual selection is required")
    if _failed_candidate(log, candidate_sha):
      raise ManualResultError("failed candidate cannot be revisited")
    evidence_id = hashlib.sha256(os.urandom(32)).hexdigest()
    if evidence_ref is None:
      evidence_ref = (log.relative_to(Path(root).resolve()).as_posix()
                      + "#manualEvidenceId=" + evidence_id)
    event = {
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "testSHA": candidate_sha, "kind": "manual-integration",
      "result": result, "runner": "local", "manualCase": current.name,
      "definitionDigest": current.definition_digest,
      "operator": operator, "evidenceRef": evidence_ref,
      "manualEvidenceId": evidence_id,
    }
    _atomic(pending, {"schema": 1, "phase": "append", "event": event})
    _append(log, event)
    if not _matching_event(log, event):
      raise ManualResultError("manual evidence append readback UNKNOWN")
    _atomic(pending, {"schema": 1, "phase": "handoff", "event": event})
    if result == "failed":
      failure = on_failure or apply_manual_failure
      _verified_handoff(failure(Path(root), issue, candidate_sha))
    _atomic(pending, {"schema": 1, "phase": "consume", "event": event})
    _consume(selection)
    _clear_pending(pending)
    return ManualOutcome(current.name, candidate_sha, result,
                         event["manualEvidenceId"], str(log), True)


def reconcile_manual_result(root: Path, issue: int, candidate_sha: str, *,
                            cases=None, on_failure=None) -> ManualOutcome | None:
  """Read back an interrupted append, never append evidence blindly again."""
  _validate_current(root, candidate_sha)
  selection, pending, lock = _paths(root, issue)
  log = _evidence_path(root, issue)
  with _guard(lock):
    journal = _read(pending)
    if journal is None:
      return None
    if not isinstance(journal, dict) or set(journal) != {"schema", "phase", "event"} \
        or journal["schema"] != 1 or journal["phase"] not in {"append", "handoff", "consume"} \
        or not isinstance(journal["event"], dict):
      raise ManualResultError("invalid pending manual journal")
    event = journal["event"]
    if event.get("testSHA") != candidate_sha:
      raise ManualResultError("stale pending candidate requires repair")
    if not _matching_event(log, event):
      raise ManualResultError("pending append absent: explicit repair required")
    if journal["phase"] == "append":
      _atomic(pending, {"schema": 1, "phase": "handoff", "event": event})
    if event["result"] == "failed" and journal["phase"] != "consume":
      raise ManualResultError(
        "manual FAIL handoff readback required before retry; "
        "version transition cannot be repeated blindly"
      )
    if journal["phase"] != "consume":
      _atomic(pending, {"schema": 1, "phase": "consume", "event": event})
    _consume(selection)
    _clear_pending(pending)
    return ManualOutcome(event["manualCase"], candidate_sha, event["result"],
                         event["manualEvidenceId"], str(log), True)


def require_manual_completion(root: Path, issue: int, candidate_sha: str, *,
                              cases=None) -> tuple[str, ...]:
  """Acceptance/CAS precondition; never treats a partial PASS as complete."""
  _validate_current(root, candidate_sha)
  selection, pending, _ = _paths(root, issue)
  if _read(pending) is not None:
    raise ManualResultError("manual outcome is UNKNOWN; progression forbidden")
  if _failed_candidate(_evidence_path(root, issue), candidate_sha):
    raise ManualResultError("MIT FAIL rejects exact candidate; progression forbidden")
  if _active(root, issue, candidate_sha, cases) is not None:
    raise ManualResultError("manual case is still active; progression forbidden")
  declared = _cases(root, issue, cases)
  if not declared:
    return ()
  succeeded = set()
  for record in _events(_evidence_path(root, issue)):
    if record.get("kind") != "manual-integration" or record.get("testSHA") != candidate_sha:
      continue
    if record["result"] == "succeeded":
      succeeded.add((record["manualCase"], record["definitionDigest"]))
  required = {(case.name, case.definition_digest) for case in declared}
  if not required.issubset(succeeded):
    raise ManualResultError("required manual integration cases are incomplete")
  return tuple(sorted(case.name for case in declared))


def read_manual_case_results(root: Path, issue: int, candidate_sha: str, *,
                             cases=None) -> dict[str, str]:
  """Read only terminal results for exact current declared definitions.

  This service never upgrades an operator assertion into provider PASS.
  """
  _validate_current(root, candidate_sha)
  _, pending, _ = _paths(root, issue)
  if _read(pending) is not None:
    raise ManualResultError("manual outcome UNKNOWN; reconcile before use")
  declared = {case.name: case.definition_digest
              for case in _cases(root, issue, cases)}
  observed = {}
  for event in _events(_evidence_path(root, issue)):
    if event.get("kind") != "manual-integration" or event.get("testSHA") != candidate_sha:
      continue
    name = event["manualCase"]
    if name not in declared:
      raise ManualResultError("manual result references undeclared test")
    if event["result"] == "failed":
      observed[name] = "failed"
      continue
    if event["definitionDigest"] != declared[name]:
      continue  # stale PASS never satisfies a changed definition
    if name in observed and observed[name] != event["result"]:
      raise ManualResultError("conflicting manual case results")
    observed[name] = event["result"]
  return observed
