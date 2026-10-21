"""Private durable selection state for exactly one manual integration case.

The canonical test evidence lives exclusively in testResults-N.jsonl, never here.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ManualSelectionError(ValueError):
  """Fail closed; neither selection nor evidence can be inferred."""


@dataclass(frozen=True)
class ManualSelection:
  issue: int
  candidate_sha: str
  name: str
  definition_digest: str


def _issue(issue: int) -> int:
  if type(issue) is not int or issue <= 0:
    raise ManualSelectionError("manual issue must be a positive integer")
  return issue


def _sha(sha: str) -> str:
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise ManualSelectionError("manual candidate must be an exact Git SHA")
  return sha


def _paths(root: Path, issue: int) -> tuple[Path, Path, Path]:
  directory = Path(root).resolve() / ".repoworkflow" / "manual"
  return (
    directory / f"active-{_issue(issue)}.json",
    directory / f"pending-{issue}.json",
    directory / f"lock-{issue}",
  )


def _read(path: Path) -> object | None:
  if path.is_symlink():
    raise ManualSelectionError("manual state path is a symlink")
  try:
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda value: _reject(value),
                      object_pairs_hook=_unique)
  except FileNotFoundError:
    return None
  except (OSError, ValueError, UnicodeError) as error:
    raise ManualSelectionError("manual state cannot be validated") from error


def _reject(value: str):
  raise ManualSelectionError("invalid manual JSON constant: " + value)


def _unique(pairs: list[tuple[str, object]]) -> dict:
  result = {}
  for key, value in pairs:
    if key in result:
      raise ManualSelectionError("duplicate manual JSON key")
    result[key] = value
  return result


def _atomic(path: Path, value: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  if path.is_symlink():
    raise ManualSelectionError("manual state path is a symlink")
  temporary = None
  try:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".manual-", delete=False) as out:
      temporary = Path(out.name)
      out.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
      out.flush()
      os.fsync(out.fileno())
    os.replace(temporary, path)
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


@contextmanager
def _guard(path: Path):
  path.parent.mkdir(parents=True, exist_ok=True)
  try:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
  except FileExistsError as error:
    raise ManualSelectionError("manual selection is locked; reconciliation required") from error
  try:
    os.close(fd)
    yield
  finally:
    path.unlink(missing_ok=True)


def _cases(root: Path, issue: int, cases):
  if cases is None:
    from .manual_test_catalogue import read_manual_cases
    cases = read_manual_cases(root, issue)
  items = tuple(cases)
  if len({case.name for case in items}) != len(items):
    raise ManualSelectionError("ambiguous manual catalogue cases")
  for case in items:
    if (not isinstance(case.name, str)
        or re.fullmatch(rf"issue-{issue}-manual--[A-Za-z0-9][A-Za-z0-9_-]*",
                        case.name) is None
        or not isinstance(case.definition_digest, str)
        or _DIGEST.fullmatch(case.definition_digest) is None):
      raise ManualSelectionError("invalid manual catalogue case")
  return items


def _validate_current(root: Path, candidate_sha: str) -> None:
  from .git import changed_files, head_sha
  if head_sha(root) != _sha(candidate_sha):
    raise ManualSelectionError("manual candidate is not current HEAD")
  dirty = [path for path in changed_files(root)
           if not path.startswith(".repoworkflow/manual/")
           and not path.startswith(".repoworkflow/validation/")]
  if dirty:
    raise ManualSelectionError("manual candidate has changed source inputs")


def _active(root: Path, issue: int, candidate_sha: str, cases):
  selection, pending, _ = _paths(root, issue)
  if _read(pending) is not None:
    raise ManualSelectionError("manual outcome pending recovery; no progression")
  raw = _read(selection)
  if raw is None:
    return None
  if not isinstance(raw, dict) or set(raw) != {"schema", "active"} or raw["schema"] != 1:
    raise ManualSelectionError("invalid manual selection schema")
  active = raw["active"]
  if not isinstance(active, list):
    raise ManualSelectionError("invalid active manual selection")
  if len(active) > 1:
    raise ManualSelectionError("multiple active manual selections")
  if not active:
    return None
  item = active[0]
  if not isinstance(item, dict) or set(item) != {
    "issue", "candidate_sha", "name", "definition_digest"
  }:
    raise ManualSelectionError("invalid active manual selection record")
  if item["issue"] != issue or item["candidate_sha"] != candidate_sha:
    raise ManualSelectionError("stale manual selection candidate/issue")
  matching = [case for case in _cases(root, issue, cases)
              if case.name == item["name"]
              and case.definition_digest == item["definition_digest"]]
  if len(matching) != 1:
    raise ManualSelectionError("stale or invalid manual test definition")
  return ManualSelection(**item)


def read_active_manual_selection(root: Path, issue: int, candidate_sha: str, *,
                                 cases=None) -> ManualSelection | None:
  """Read back selection; reject stale, ambiguous and journal-pending state."""
  _issue(issue)
  _validate_current(root, candidate_sha)
  return _active(root, issue, candidate_sha, cases)


def select_manual_case(root: Path, issue: int, candidate_sha: str, case, *,
                       cases=None) -> ManualSelection:
  """Persist one explicit case, refusing to overwrite an active case."""
  _issue(issue)
  _validate_current(root, candidate_sha)
  selection, pending, lock = _paths(root, issue)
  with _guard(lock):
    if _read(pending) is not None:
      raise ManualSelectionError("manual outcome pending recovery")
    from .manual_test_result import _evidence_path, _failed_candidate
    if _failed_candidate(_evidence_path(root, issue), candidate_sha):
      raise ManualSelectionError("failed candidate cannot be revisited")
    if _active(root, issue, candidate_sha, cases) is not None:
      raise ManualSelectionError("manual case already actively selected")
    matching = [item for item in _cases(root, issue, cases)
                if item.name == getattr(case, "name", None)
                and item.definition_digest == getattr(case, "definition_digest", None)]
    if len(matching) != 1:
      raise ManualSelectionError("manual case is not declared for this candidate")
    chosen = ManualSelection(issue, candidate_sha,
                             matching[0].name, matching[0].definition_digest)
    _atomic(selection, {"schema": 1, "active": [vars(chosen)]})
    if _active(root, issue, candidate_sha, cases) != chosen:
      raise ManualSelectionError("manual selection readback UNKNOWN")
    return chosen
