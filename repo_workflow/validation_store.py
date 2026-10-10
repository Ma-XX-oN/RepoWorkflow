"""Append-only durable validation evidence using #101 state-store primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from .state_store import JsonRecordStore, StateStoreError, WriterIdentity
from .validation_coverage import Evidence as CoverageEvidence


SCHEMA = 1
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\\Z")
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\\Z")


class ValidationStoreError(RuntimeError):
  """Invalid or conflicting durable validation record."""


@dataclass(frozen=True)
class ValidationObservation:
  record_id: str
  candidate_sha: str
  version: str
  branch: str
  unit: str
  fingerprint: str
  verdict: str
  mode: str
  runner: str
  platform: str
  provider_run: str

  def __post_init__(self) -> None:
    if not isinstance(self.record_id, str) or not _ID.fullmatch(self.record_id):
      raise ValidationStoreError("invalid validation record ID")
    if not isinstance(self.candidate_sha, str) or not _SHA.fullmatch(self.candidate_sha):
      raise ValidationStoreError("invalid exact candidate SHA")
    for field in ("version", "branch", "runner", "platform", "provider_run"):
      value = getattr(self, field)
      if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationStoreError(f"invalid evidence {field}")
    try:
      CoverageEvidence(self.unit, self.fingerprint, self.verdict,
                       self.mode, self.provider_run)
    except (ValueError, TypeError) as error:
      raise ValidationStoreError(f"invalid coverage evidence: {error}") from error

  def coverage(self) -> CoverageEvidence:
    return CoverageEvidence(self.unit, self.fingerprint, self.verdict,
                            self.mode, self.provider_run)


def _canonical(value: dict) -> bytes:
  return json.dumps(value, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False).encode("ascii")


def _payload(value: ValidationObservation) -> dict:
  return {"schema": SCHEMA, **asdict(value)}


def _digest(payload: dict) -> str:
  return hashlib.sha256(_canonical(payload)).hexdigest()


class ValidationEvidenceStore:
  """Durable per-observation immutable create-only records.

  Each independent observation has a stable ID supplied by the producer.
  Distinct IDs occupy independent #101 CAS records. Mutation is not exposed.
  """

  def __init__(self, repository_root: Path):
    root = Path(repository_root).resolve()
    self.records = JsonRecordStore(root / ".repoworkflow" / "validation")

  def publish(self, observation: ValidationObservation,
              writer: WriterIdentity) -> dict:
    if not isinstance(observation, ValidationObservation):
      raise ValidationStoreError("expected a validation observation")
    payload = _payload(observation)
    value = {"payload": payload, "digest": _digest(payload)}
    try:
      return self.records.create(self._key(observation.record_id), value, writer)
    except StateStoreError as error:
      raise ValidationStoreError(str(error)) from error

  def read(self, record_id: str) -> ValidationObservation:
    key = self._key(record_id)
    try:
      record = self.records.read(key)
    except StateStoreError as error:
      raise ValidationStoreError(str(error)) from error
    value = record["value"]
    if not isinstance(value, dict) or set(value) != {"payload", "digest"}:
      raise ValidationStoreError("invalid validation storage envelope")
    payload = value["payload"]
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
      raise ValidationStoreError("unsupported validation payload schema")
    if not isinstance(value["digest"], str) or value["digest"] != _digest(payload):
      raise ValidationStoreError("validation payload digest mismatch")
    fields = set(ValidationObservation.__dataclass_fields__)
    if set(payload) != fields | {"schema"}:
      raise ValidationStoreError("unsupported validation payload fields")
    try:
      observation = ValidationObservation(**{field: payload[field] for field in fields})
    except (TypeError, ValueError) as error:
      raise ValidationStoreError(str(error)) from error
    if observation.record_id != record_id:
      raise ValidationStoreError("validation record identity mismatch")
    return observation

  def list_ids(self) -> tuple[str, ...]:
    folder = self.records.root / "records"
    if not folder.exists():
      return ()
    if not folder.is_dir() or folder.is_symlink():
      raise ValidationStoreError("invalid validation record directory")
    result = []
    for path in folder.iterdir():
      if path.suffix != ".json" or not path.is_file() or path.is_symlink():
        raise ValidationStoreError("unexpected validation record")
      identifier = path.stem
      self._key(identifier)
      self.read(identifier)
      result.append(identifier)
    return tuple(sorted(result))

  @staticmethod
  def _key(record_id: str) -> str:
    if not isinstance(record_id, str) or not _ID.fullmatch(record_id):
      raise ValidationStoreError("invalid validation record ID")
    return f"records/{record_id}"
