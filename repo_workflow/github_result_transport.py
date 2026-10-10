"""Exact-identity GitHub Actions artifact bundle transport for repo-ci v1.

GitHub Actions upload/download transfer the bundle. This module validates
contents after retrieval; the caller separately authenticates workflow/run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


class TransportError(ValueError):
  """Missing, conflicting, invalid, or corrupt transport evidence."""


def _identity(value: object, field: str) -> str:
  if not isinstance(value, str) or not _ID.fullmatch(value):
    raise TransportError(f"invalid {field}")
  return value


def _candidate(value: object) -> dict:
  if not isinstance(value, dict) or set(value) != {"repository", "commit", "base"}:
    raise TransportError("candidate requires repository, commit, and base")
  if not all(isinstance(v, str) and v for v in value.values()):
    raise TransportError("invalid candidate identity")
  return dict(value)


def _manifest(request: dict, records: dict[str, bytes]) -> dict:
  if not isinstance(request, dict) or type(request.get("contract_version")) is not int or request["contract_version"] != 1:
    raise TransportError("unsupported contract version")
  if request.get("operation") != "publish":
    raise TransportError("operation must be publish")
  invocation = _identity(request.get("invocation_id"), "invocation_id")
  candidate = _candidate(request.get("candidate"))
  requirements = request.get("requirements")
  if not isinstance(requirements, dict):
    raise TransportError("missing requirements")
  declared = requirements.get("artifacts")
  if not isinstance(declared, list) or any(not isinstance(x, str) for x in declared):
    raise TransportError("invalid artifact declarations")
  if len(declared) != len(set(declared)):
    raise TransportError("duplicate artifact declaration")
  if not isinstance(records, dict) or set(records) != set(declared):
    raise TransportError("records must match declared artifacts")
  entries = []
  for name in sorted(records):
    _identity(name, "artifact name")
    data = records[name]
    if not isinstance(data, bytes):
      raise TransportError("artifact contents must be bytes")
    entries.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data)})
  return {"contract_version": 1, "invocation_id": invocation,
          "candidate": candidate, "artifacts": entries}


def publish_bundle(request: dict, records: dict[str, bytes], directory: Path) -> dict:
  """Create an artifact bundle. A preexisting destination is a conflict."""
  manifest = _manifest(request, records)
  directory = Path(directory)
  if directory.exists():
    raise TransportError("bundle destination already exists")
  directory.mkdir(parents=True, exist_ok=False)
  try:
    for entry in manifest["artifacts"]:
      (directory / entry["name"]).write_bytes(records[entry["name"]])
    (directory / "manifest.json").write_text(
      json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
  except BaseException:
    for child in directory.iterdir():
      if child.is_file() or child.is_symlink():
        child.unlink()
    directory.rmdir()
    raise
  return manifest


def fetch_bundle(directory: Path, expected_invocation: str,
                 expected_candidate: dict, declared: list[str]) -> dict[str, bytes]:
  """Fail closed unless all declared retrieved records match exact identity."""
  directory = Path(directory)
  _identity(expected_invocation, "invocation_id")
  expected_candidate = _candidate(expected_candidate)
  if not isinstance(declared, list) or any(not isinstance(x, str) for x in declared):
    raise TransportError("invalid artifact declaration")
  if len(declared) != len(set(declared)):
    raise TransportError("duplicate artifact declaration")
  for name in declared:
    _identity(name, "artifact name")
  try:
    path = directory / "manifest.json"
    if path.is_symlink() or not path.is_file():
      raise TransportError("missing manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise TransportError("missing or corrupt manifest") from exc
  if (not isinstance(manifest, dict)
      or set(manifest) != {"contract_version", "invocation_id", "candidate", "artifacts"}
      or type(manifest["contract_version"]) is not int
      or manifest["contract_version"] != 1):
    raise TransportError("invalid manifest envelope")
  if (manifest["invocation_id"] != expected_invocation
      or manifest["candidate"] != expected_candidate):
    raise TransportError("candidate or invocation identity mismatch")
  entries = manifest["artifacts"]
  if not isinstance(entries, list) or len(entries) != len(declared):
    raise TransportError("incomplete artifact set")
  result = {}
  for entry in entries:
    if not isinstance(entry, dict) or set(entry) != {"name", "sha256", "size"}:
      raise TransportError("invalid artifact entry")
    name = _identity(entry["name"], "artifact name")
    if name in result or name not in declared:
      raise TransportError("duplicate or undeclared artifact")
    if (not isinstance(entry["sha256"], str)
        or not _HEX.fullmatch(entry["sha256"])
        or type(entry["size"]) is not int or entry["size"] < 0):
      raise TransportError("invalid artifact digest or size")
    path = directory / name
    if path.is_symlink() or not path.is_file():
      raise TransportError("missing or unsafe artifact")
    try:
      data = path.read_bytes()
    except OSError as exc:
      raise TransportError("cannot retrieve artifact") from exc
    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
      raise TransportError("artifact integrity failed")
    result[name] = data
  if set(result) != set(declared):
    raise TransportError("incomplete artifact membership")
  if {p.name for p in directory.iterdir()} != set(declared) | {"manifest.json"}:
    raise TransportError("unexpected bundle members")
  return result
