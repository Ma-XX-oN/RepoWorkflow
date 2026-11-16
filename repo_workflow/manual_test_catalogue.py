"""Read declarative manual integration cases from the canonical test catalogue.

No operation in this module executes a test harness or changes repository state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .test_catalogue import CATALOGUE_PATH, TestCatalogueError, parse_test_catalogue


MANUAL_CASE_RE = re.compile(
  r"issue-([1-9][0-9]*)-manual--([A-Za-z0-9][A-Za-z0-9_-]*)\Z",
  re.ASCII,
)
_MANUAL_PREFIX_RE = re.compile(r"\Aissue-[^-]+-manual--", re.ASCII)
_MANUAL_FIELDS = frozenset({"type", "instructions", "expected_result"})


class ManualCatalogueError(ValueError):
  """A manual-case declaration is missing, inconsistent, or ambiguous."""


@dataclass(frozen=True)
class ManualCase:
  name: str
  instructions: str
  expected_result: str
  definition_digest: str


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
  """Fail on repeated JSON keys, including duplicates within one group object."""
  result: dict = {}
  for key, value in pairs:
    if key in result:
      raise ManualCatalogueError(f"duplicate JSON key: {key}")
    result[key] = value
  return result


def _load_catalogue(root: Path) -> dict:
  path = Path(root) / CATALOGUE_PATH
  try:
    contents = path.read_text(encoding="utf-8")
    catalogue = json.loads(contents, object_pairs_hook=_unique_pairs)
  except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise ManualCatalogueError(f"cannot read {path}: {error}") from error
  try:
    parse_test_catalogue(catalogue)
  except TestCatalogueError as error:
    raise ManualCatalogueError(f"invalid {path}: {error}") from error
  return catalogue


def _digest(name: str, metadata: dict, harness_name: str, harness: dict) -> str:
  canonical = json.dumps(
    {
      "schema": "rwf-manual-case-v1",
      "name": name,
      "metadata": metadata,
      "test-harness": harness_name,
      "harness-definition": harness,
    },
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
  )
  return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_manual_cases(root: Path, issue: int) -> tuple[ManualCase, ...]:
  """Return validated current-issue cases ordered by complete case name.

  Foreign issues are ignored when correctly declared. Malformed manual
  declarations anywhere in the catalogue fail closed, not silently skipped.
  """
  if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
    raise ManualCatalogueError("issue must be a positive integer")

  catalogue = _load_catalogue(root)
  cases: list[ManualCase] = []
  declared_manual_names: set[str] = set()
  harnesses = catalogue["test-harnesses"]
  for index, declaration in enumerate(catalogue["tests"]):
    harness_name = declaration["test-harness"]
    for name, metadata in declaration.items():
      if name in {"test-harness", "command"}:
        continue
      manual_name = MANUAL_CASE_RE.fullmatch(name)
      manual_prefix = _MANUAL_PREFIX_RE.match(name) is not None
      manual_type = metadata.get("type") == "manual"
      if not (manual_name or manual_prefix or manual_type):
        continue
      if manual_name is None:
        raise ManualCatalogueError(f"invalid manual case name: {name}")
      if not manual_type:
        raise ManualCatalogueError(f"manual case {name} requires type=manual")
      if "command" in declaration:
        raise ManualCatalogueError(
          f"manual case {name} cannot declare executable command override"
        )
      declared_manual_names.add(name)
      if metadata.keys() != _MANUAL_FIELDS:
        raise ManualCatalogueError(
          f"manual case {name} requires exactly: type, instructions, expected_result"
        )
      for field in ("instructions", "expected_result"):
        value = metadata[field]
        if not isinstance(value, str) or not value.strip():
          raise ManualCatalogueError(
            f"manual case {name} requires nonempty {field}"
          )
      harness = harnesses.get(harness_name)
      if not isinstance(harness, dict):
        raise ManualCatalogueError(
          f"manual case {name} references unknown test harness: {harness_name}"
        )
      if manual_name.group(1) != str(issue):
        continue
      cases.append(ManualCase(
        name=name,
        instructions=metadata["instructions"],
        expected_result=metadata["expected_result"],
        definition_digest=_digest(name, metadata, harness_name, harness),
      ))
  for alias, members in catalogue.get("aliases", {}).items():
    if any(member in declared_manual_names for member in members):
      raise ManualCatalogueError(
        f"test alias {alias} cannot include a manual case"
      )
  return tuple(sorted(cases, key=lambda case: case.name))


def find_manual_case(root: Path, issue: int, name: str) -> ManualCase:
  """Resolve exactly one declared manual case for the current issue."""
  if not isinstance(name, str) or MANUAL_CASE_RE.fullmatch(name) is None:
    raise ManualCatalogueError(f"invalid manual case name: {name!r}")
  for case in read_manual_cases(root, issue):
    if case.name == name:
      return case
  raise ManualCatalogueError(
    f"manual case {name} is not declared for issue {issue}"
  )
