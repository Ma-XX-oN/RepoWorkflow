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
  ManualSelection, ManualSelectionError, _active, _atomic, _cases,
  _guard, _issue, _paths, _read, _validate_current,
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
  dependency_satisfied: bool
  version_before: str
  version_after: str
  repair_owner: str


def _verified_handoff(value: object) -> None:
  if not isinstance(value, FailureHandoff):
    raise ManualResultError("manual FAIL has no verified repair handoff")
  before = _version_components(value.version_before)
  after = _version_components(value.version_after)
  if (value.lifecycle != "active" or value.dependency_satisfied is not False
      or before is None or after != (before[0] + 1, 0)
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
  """Use canonical lifecycle and version adapters; fail on partial handoff.

  The current repository adapter returns R=1 after rejection. The expected
  R=0 contract therefore needs an adapter fix outside this ticket's files.
  """
  from .lifecycle_store import LifecycleStore
  from .state_store import WriterIdentity
  from .version_adapter import run_transition, read_development_version
  from .config import load_config

  writer_id, session_id = os.environ.get("RWF_WRITER_ID"), os.environ.get("RWF_SESSION_ID")
  if not writer_id or not session_id:
    raise ManualResultError("failure handoff requires RWF_WRITER_ID and RWF_SESSION_ID")
  store = LifecycleStore(root)
  snapshot = store.read(issue)
  state = snapshot.lifecycle.state
  if state in {"in_review", "accepted"}:
    store.transition(
      issue, "reject/reopen", candidate_sha,
      snapshot.lifecycle.relationship_revision,
      WriterIdentity(writer_id, session_id), snapshot.revision,
    )
  elif state != "active":
    raise ManualResultError("manual FAIL cannot reopen lifecycle state " + state)
  observed = store.read(issue).lifecycle
  if observed.state != "active" or observed.dependency_satisfied:
    raise ManualResultError("manual FAIL lifecycle rejection readback UNKNOWN")
  config = load_config(root)
  before = read_development_version(root, config)
  transition = run_transition(root, config, "task", "--increment",
                              "merge-integration-failed")
  after = read_development_version(root, config)
  previous, current = _version_components(before), _version_components(after)
  if (transition.before != before or transition.after != after
      or previous is None or current != (previous[0] + 1, 0)):
    raise ManualResultError(
      "version adapter transition does not satisfy Q += 1, R = 0; "
      f"observed {before} -> {after}; repair handoff required"
    )
  return FailureHandoff(observed.state, False, before, after,
                        f"RWF #{issue} repair owner")


def record_manual_result(
  root: Path, issue: int, candidate_sha: str,
  result: Literal["succeeded", "failed"], *,
  operator: str, evidence_ref: str, cases=None,
  on_failure: Callable[[Path, int, str], object] | None = None,
) -> ManualOutcome:
  """Write once, read back and consume exactly one active case.

  On a failure, result evidence precedes lifecycle/version mutation. Any
  interrupted or rejected handoff leaves a durable blocking journal.
  """
  if result not in ("succeeded", "failed"):
    raise ManualResultError("invalid manual result (TIMEOUT must be deferred)")
  if (not isinstance(operator, str) or not operator.strip()
      or not isinstance(evidence_ref, str) or not evidence_ref.strip()):
    raise ManualResultError("operator and evidence reference are required")
  _validate_current(root, candidate_sha)
  selection, pending, lock = _paths(root, issue)
  log = _evidence_path(root, issue)
  with _guard(lock):
    current = _active(root, issue, candidate_sha, cases)
    if current is None:
      raise ManualResultError("exactly one active manual selection is required")
    if _failed_candidate(log, candidate_sha):
      raise ManualResultError("failed candidate cannot be revisited")
    event = {
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "testSHA": candidate_sha, "kind": "manual-integration",
      "result": result, "runner": "local", "manualCase": current.name,
      "definitionDigest": current.definition_digest,
      "operator": operator.strip(), "evidenceRef": evidence_ref.strip(),
      "manualEvidenceId": hashlib.sha256(os.urandom(32)).hexdigest(),
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
