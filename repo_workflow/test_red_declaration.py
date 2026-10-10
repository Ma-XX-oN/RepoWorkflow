"""Pre-execution expected-RED declarations from the existing test catalogue."""
from __future__ import annotations

import json
from pathlib import Path

from .test_red_classification import RedExpectation


GENERIC_SIGNATURES = frozenset({
  "error", "failed", "failure", "fail", "assertionerror",
  "traceback", "exception", "test failed", "tests failed",
})


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
  result = {}
  for key, value in pairs:
    if key in result:
      raise ValueError("duplicate RED catalogue field")
    result[key] = value
  return result


def red_declaration(root: Path, group: str) -> tuple[RedExpectation | None, str]:
  """Never derive expectations from the observed subprocess response."""
  try:
    catalogue = json.loads(
      (root / ".ci/tests.json").read_text(encoding="utf-8"),
      object_pairs_hook=_unique_json_object,
    )
  except (OSError, ValueError, UnicodeError):
    return None, "invalid-expected-failure-declaration"
  if not isinstance(catalogue, dict) or not isinstance(
    catalogue.get("tests"), list,
  ):
    return None, "invalid-expected-failure-declaration"
  matches = [
    entry[group]
    for entry in catalogue["tests"]
    if isinstance(entry, dict) and group in entry
  ]
  if len(matches) != 1 or not isinstance(matches[0], dict):
    return None, "invalid-expected-failure-declaration"
  if "expected-red" not in matches[0]:
    return None, "expected-failure-declaration-missing"
  declared = matches[0]["expected-red"]
  if (
    not isinstance(declared, dict)
    or set(declared) != {"exit-code", "output-contains"}
  ):
    return None, "invalid-expected-failure-declaration"
  exit_code = declared["exit-code"]
  signature = declared["output-contains"]
  if (
    type(exit_code) is not int or exit_code <= 0
    or not isinstance(signature, str)
    or not signature.strip()
    or signature.strip().casefold() in GENERIC_SIGNATURES
    or any(0xD800 <= ord(c) <= 0xDFFF for c in signature)
  ):
    return None, "invalid-expected-failure-declaration"
  return RedExpectation(exit_code, signature), ""
