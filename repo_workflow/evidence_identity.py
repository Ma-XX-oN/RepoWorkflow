"""Provider-neutral validation evidence identity contract (issue #68)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping


SCHEMA = "rwf-validation-input-v1"
SECTIONS = ("source", "catalogue", "configuration", "workflow", "capabilities")
_HEX256 = re.compile(r"[0-9a-f]{64}\\Z")


def _name(value: object, what: str) -> str:
  if not isinstance(value, str) or not value or value.strip() != value:
    raise ValueError(f"{what} must be a nonempty unpadded string")
  if unicodedata.normalize("NFC", value) != value:
    raise ValueError(f"{what} must use NFC Unicode")
  if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
    raise ValueError(f"{what} contains control characters")
  return value


def manifest(unit: str, *, source: Mapping[str, str],
             catalogue: Mapping[str, str], configuration: Mapping[str, str],
             workflow: Mapping[str, str],
             capabilities: Mapping[str, str]) -> dict:
  """Return an immutable-by-convention, canonicalizable input snapshot.

  All five sections must be supplied explicitly. Every file-section value
  is the lowercase SHA-256 of exact bytes, not a timestamp or Git path SHA.
  Capabilities map required semantic feature identifiers to versioned values.
  The caller must enumerate the complete per-unit dependency closure.
  """
  result: dict = {"schema": SCHEMA, "unit": _name(unit, "unit")}
  entries_by_section = {
    "source": source, "catalogue": catalogue,
    "configuration": configuration, "workflow": workflow,
    "capabilities": capabilities,
  }
  for section in SECTIONS:
    entries = entries_by_section[section]
    if not isinstance(entries, Mapping) or not entries:
      raise ValueError(f"{section} requires a nonempty mapping")
    normalized: dict[str, str] = {}
    for key, value in entries.items():
      key = _name(key, f"{section} key")
      if key in normalized:
        raise ValueError(f"duplicate {section} key")
      value = _name(value, f"{section} value")
      if section != "capabilities" and not _HEX256.fullmatch(value):
        raise ValueError(f"{section} requires lowercase SHA-256 byte digests")
      normalized[key] = value
    result[section] = normalized
  return result


def canonical_bytes(value: Mapping) -> bytes:
  """Strictly validate externally loaded manifests before hashing."""
  if not isinstance(value, Mapping):
    raise ValueError("manifest must be a mapping")
  if set(value) != {"schema", "unit", *SECTIONS} or value["schema"] != SCHEMA:
    raise ValueError("unsupported evidence identity schema or fields")
  normalized = manifest(value["unit"], **{key: value[key] for key in SECTIONS})
  return json.dumps(normalized, ensure_ascii=True, sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode("ascii")


def fingerprint(value: Mapping) -> str:
  """Content identity shared by local and hosted executions."""
  return hashlib.sha256(canonical_bytes(value)).hexdigest()
