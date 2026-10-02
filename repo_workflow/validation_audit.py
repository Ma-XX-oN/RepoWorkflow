from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Iterable


_TASK_VERSION_RE = re.compile(
  r"^(?P<base>\d+\.\d+\.\d+)-issue\."
  r"(?P<issue>\d+)\.(?P<generation>\d+)\.(?P<iteration>\d+)$"
)
_STABLE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_PRELIM_TAG_RE = re.compile(
  r"^v\d+\.\d+\.\d+-PRELIM-(?P<issue>\d+)\."
  r"(?P<generation>\d+)\.(?P<iteration>\d+)$"
)
_KINDS = {"regression", "integration"}
_RESULTS = {"succeeded", "failed", "incomplete"}


class ValidationAuditError(RuntimeError):
  pass


@dataclass(frozen=True)
class ValidationRecord:
  timestamp: str
  kind: str
  baseVersion: str
  branch: str
  testVersion: str
  testSHA: str
  candidateTag: str | None
  result: str
  runner: str

  def validate(self) -> None:
    if self.kind not in _KINDS:
      raise ValidationAuditError(f"invalid validation kind: {self.kind}")
    if self.result not in _RESULTS:
      raise ValidationAuditError(f"invalid validation result: {self.result}")
    if not self.branch:
      raise ValidationAuditError("validation branch must not be empty")
    if not self.runner:
      raise ValidationAuditError("validation runner must not be empty")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", self.testSHA):
      raise ValidationAuditError("validation testSHA is not a commit id")
    match = _TASK_VERSION_RE.fullmatch(self.testVersion)
    if match is not None:
      if match.group("base") != self.baseVersion:
        raise ValidationAuditError(
          "validation baseVersion does not match testVersion base"
        )
    elif _STABLE_VERSION_RE.fullmatch(self.testVersion) is None:
      raise ValidationAuditError(
        "validation testVersion is not a task or stable version"
      )
    try:
      parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
      raise ValidationAuditError("validation timestamp is not ISO-8601") from exc
    if parsed.tzinfo is None:
      raise ValidationAuditError("validation timestamp must include timezone")

  @property
  def issue(self) -> int:
    match = _TASK_VERSION_RE.fullmatch(self.testVersion)
    if match is not None:
      return int(match.group("issue"))
    if self.candidateTag is not None:
      prelim = _PRELIM_TAG_RE.fullmatch(self.candidateTag)
      if prelim is not None:
        return int(prelim.group("issue"))
    raise ValidationAuditError(
      "stable validation record requires a PRELIM candidate tag "
      "to identify its issue"
    )

  def to_json(self) -> str:
    self.validate()
    return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

  @classmethod
  def from_json(cls, text: str) -> "ValidationRecord":
    try:
      value = json.loads(text)
    except json.JSONDecodeError as exc:
      raise ValidationAuditError("invalid validation JSON record") from exc
    if not isinstance(value, dict):
      raise ValidationAuditError("validation record must be a JSON object")
    expected = {
      "timestamp",
      "kind",
      "baseVersion",
      "branch",
      "testVersion",
      "testSHA",
      "candidateTag",
      "result",
      "runner",
    }
    if set(value) != expected:
      raise ValidationAuditError("validation record fields do not match schema")
    record = cls(**value)
    record.validate()
    return record


def utc_timestamp() -> str:
  return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def audit_path(root: Path, issue: int) -> Path:
  if issue < 1:
    raise ValidationAuditError("issue number must be positive")
  return root / ".repoworkflow" / "validation" / f"testResults-{issue}.jsonl"


def read_records(path: Path) -> list[ValidationRecord]:
  try:
    text = path.read_text(encoding="utf-8")
  except FileNotFoundError:
    return []
  records: list[ValidationRecord] = []
  for line_number, line in enumerate(text.splitlines(), start=1):
    if not line.strip():
      continue
    try:
      records.append(ValidationRecord.from_json(line))
    except ValidationAuditError as exc:
      raise ValidationAuditError(f"{path}:{line_number}: {exc}") from exc
  return records


def _acquire_append_lock(path: Path, *, timeout: float = 10.0) -> int:
  lock = path.with_suffix(path.suffix + ".lock")
  deadline = time.monotonic() + timeout
  while True:
    try:
      return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
      if time.monotonic() >= deadline:
        raise ValidationAuditError(
          f"timed out waiting for validation audit lock: {lock}"
        )
      time.sleep(0.01)


def _release_append_lock(path: Path, descriptor: int) -> None:
  lock = path.with_suffix(path.suffix + ".lock")
  os.close(descriptor)
  try:
    lock.unlink()
  except FileNotFoundError:
    pass


def append_record(root: Path, record: ValidationRecord) -> Path:
  record.validate()
  path = audit_path(root, record.issue)
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor = _acquire_append_lock(path)
  try:
    descriptor_out = os.open(
      path,
      os.O_CREAT | os.O_WRONLY | os.O_APPEND,
      0o666,
    )
    try:
      os.write(descriptor_out, (record.to_json() + "\n").encode("utf-8"))
      os.fsync(descriptor_out)
    finally:
      os.close(descriptor_out)
  finally:
    _release_append_lock(path, descriptor)
  return path


def records_for_sha(
  records: Iterable[ValidationRecord],
  test_sha: str,
  *,
  kind: str | None = None,
) -> list[ValidationRecord]:
  if kind is not None and kind not in _KINDS:
    raise ValidationAuditError(f"invalid validation kind: {kind}")
  return [
    record
    for record in records
    if record.testSHA == test_sha and (kind is None or record.kind == kind)
  ]


def latest_result_for_sha(
  records: Iterable[ValidationRecord],
  test_sha: str,
  *,
  kind: str,
) -> str | None:
  matches = records_for_sha(records, test_sha, kind=kind)
  if not matches:
    return None
  return matches[-1].result


def regression_reuse_decision(
  records: Iterable[ValidationRecord],
  test_sha: str,
) -> str:
  """Return `reuse-pass`, `reuse-terminal`, or `run` for an exact SHA."""
  result = latest_result_for_sha(records, test_sha, kind="regression")
  if result == "succeeded":
    return "reuse-pass"
  if result == "failed":
    return "reuse-terminal"
  return "run"
