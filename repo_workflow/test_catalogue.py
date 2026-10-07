from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


CATALOGUE_PATH = Path(".ci") / "tests.json"


class TestCatalogueError(RuntimeError):
  pass


@dataclass(frozen=True)
class TestCatalogue:
  groups: frozenset[str]
  aliases: dict[str, tuple[str, ...]]

  def alias_names(self) -> tuple[str, ...]:
    return tuple(sorted(self.aliases))

  def expand_aliases(self, names) -> tuple[str, ...]:
    if isinstance(names, str):
      names = (names,)
    try:
      requested = tuple(names)
    except TypeError as error:
      raise TestCatalogueError("alias names must be iterable") from error
    groups: set[str] = set()
    for name in requested:
      if not isinstance(name, str) or not name:
        raise TestCatalogueError("alias names must be non-empty strings")
      try:
        groups.update(self.aliases[name])
      except KeyError as error:
        raise TestCatalogueError(f"unknown test alias: {name}") from error
    return tuple(sorted(groups))

  def verification_groups(self, required_groups, aliases=()) -> tuple[str, ...]:
    if isinstance(required_groups, str):
      required_groups = (required_groups,)
    required = tuple(required_groups)
    selected: set[str] = set()
    for group in required:
      if not isinstance(group, str) or not group:
        raise TestCatalogueError("required group names must be non-empty strings")
      if group not in self.groups:
        raise TestCatalogueError(f"unknown required test group: {group}")
      selected.add(group)
    selected.update(self.expand_aliases(aliases))
    return tuple(sorted(selected))



def _group_keys(tests: object) -> frozenset[str]:
  if not isinstance(tests, list):
    raise TestCatalogueError("tests must be an array")
  groups: set[str] = set()
  for index, declaration in enumerate(tests):
    if not isinstance(declaration, dict):
      raise TestCatalogueError(f"tests[{index}] must be an object")
    harness = declaration.get("test-harness")
    if not isinstance(harness, str) or not harness:
      raise TestCatalogueError(
        f"tests[{index}].test-harness must be a non-empty string"
      )
    for key, value in declaration.items():
      if key in {"test-harness", "command"}:
        continue
      if not isinstance(key, str) or not key:
        raise TestCatalogueError("test group keys must be non-empty strings")
      if key in groups:
        raise TestCatalogueError(f"duplicate test group: {key}")
      if not isinstance(value, dict):
        raise TestCatalogueError(f"test group {key} must be an object")
      groups.add(key)
  return frozenset(groups)


def _aliases(value: object, groups: frozenset[str]) -> dict[str, tuple[str, ...]]:
  if value is None:
    return {}
  if not isinstance(value, dict):
    raise TestCatalogueError("aliases must be an object")
  result: dict[str, tuple[str, ...]] = {}
  for name, members in value.items():
    if not isinstance(name, str) or not name:
      raise TestCatalogueError("alias names must be non-empty strings")
    if not isinstance(members, list):
      raise TestCatalogueError(f"alias {name} must be an array")
    normalized: list[str] = []
    seen: set[str] = set()
    for member in members:
      if not isinstance(member, str) or not member:
        raise TestCatalogueError(
          f"alias {name} members must be non-empty strings"
        )
      if member not in groups:
        raise TestCatalogueError(
          f"alias {name} references unknown test group: {member}"
        )
      if member not in seen:
        seen.add(member)
        normalized.append(member)
    result[name] = tuple(sorted(normalized))
  return result


def parse_test_catalogue(value: object) -> TestCatalogue:
  if not isinstance(value, dict):
    raise TestCatalogueError("test catalogue must be an object")
  allowed = {"test-harnesses", "tests", "aliases"}
  unknown = sorted(set(value) - allowed)
  if unknown:
    raise TestCatalogueError(
      "test catalogue contains unsupported fields: " + ", ".join(unknown)
    )
  harnesses = value.get("test-harnesses")
  if not isinstance(harnesses, dict):
    raise TestCatalogueError("test-harnesses must be an object")
  groups = _group_keys(value.get("tests"))
  aliases = _aliases(value.get("aliases", {}), groups)
  return TestCatalogue(groups, aliases)


def load_test_catalogue(root: Path) -> TestCatalogue:
  path = Path(root) / CATALOGUE_PATH
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as error:
    raise TestCatalogueError(f"missing test catalogue: {path}") from error
  except json.JSONDecodeError as error:
    raise TestCatalogueError(f"invalid JSON in {path}: {error}") from error
  return parse_test_catalogue(value)
