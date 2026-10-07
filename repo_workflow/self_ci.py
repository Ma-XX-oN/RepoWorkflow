from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from .lifecycle_store import LifecycleStore
from .test_catalogue import load_test_catalogue


ISSUE_BRANCH_RE = re.compile(r"^issue-(\d+)(?:-|$)")
VALID_TIERS = {"issue", "regression", "integration"}


class SelfCiError(RuntimeError):
  pass


@dataclass(frozen=True)
class SelfCiPlan:
  tier: str
  issue: str | None
  groups: tuple[str, ...]
  reason: str

  def to_json_value(self) -> dict:
    return {
      "tier": self.tier,
      "issue": self.issue,
      "groups": list(self.groups),
      "reason": self.reason,
    }


def issue_from_head_ref(head_ref: str) -> str:
  match = ISSUE_BRANCH_RE.match(head_ref)
  if match is None:
    raise SelfCiError(
      "issue verification requires an issue-<N>-... branch"
    )
  return str(int(match.group(1)))


def _catalogue_value(root: Path) -> dict:
  path = Path(root) / ".ci" / "tests.json"
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise SelfCiError(f"cannot read authoritative test catalogue: {error}") from error
  load_test_catalogue(root)
  return value


def _group_records(root: Path) -> dict[str, tuple[dict, dict]]:
  value = _catalogue_value(root)
  harnesses = value["test-harnesses"]
  records: dict[str, tuple[dict, dict]] = {}
  for declaration in value["tests"]:
    harness_name = declaration["test-harness"]
    try:
      harness = harnesses[harness_name]
    except KeyError as error:
      raise SelfCiError(
        f"unknown test harness {harness_name!r}"
      ) from error
    if not isinstance(harness, dict):
      raise SelfCiError(f"test harness {harness_name!r} must be an object")
    for group, metadata in declaration.items():
      if group in {"test-harness", "command"}:
        continue
      records[group] = (declaration, metadata)
  return records


def _groups_of_type(root: Path, kind: str) -> tuple[str, ...]:
  return tuple(sorted(
    group
    for group, (_declaration, metadata) in _group_records(root).items()
    if metadata.get("type") == kind
  ))


def issue_verification_groups(root: Path, issue: str) -> tuple[str, ...]:
  catalogue = load_test_catalogue(root)
  prefix = f"issue-{issue}-"
  owned = tuple(sorted(group for group in catalogue.groups if group.startswith(prefix)))
  if not owned:
    raise SelfCiError(
      f"issue {issue} has no verification group in .ci/tests.json"
    )

  lifecycle = LifecycleStore(root).read(issue).lifecycle
  selected = set(catalogue.verification_groups(
    owned,
    lifecycle.high_risk_aliases,
  ))
  selected.update(_groups_of_type(root, "invariant"))
  return tuple(sorted(selected))


def plan_self_ci(
  root: Path,
  *,
  event: str,
  ref: str,
  head_ref: str,
  classification: str,
  requested_tier: str = "",
) -> SelfCiPlan:
  if requested_tier and requested_tier not in VALID_TIERS:
    raise SelfCiError(f"unsupported requested CI tier: {requested_tier}")

  if event == "push" and ref == "refs/heads/main":
    return SelfCiPlan(
      "integration",
      None,
      (),
      "authoritative main integration candidate",
    )

  if requested_tier in {"regression", "integration"}:
    return SelfCiPlan(
      requested_tier,
      None,
      (),
      f"explicit {requested_tier} verification request",
    )

  if classification == "fast" and not requested_tier:
    return SelfCiPlan("docs", None, (), "documentation-only fast path")

  if event == "pull_request" or requested_tier == "issue":
    issue = issue_from_head_ref(head_ref or ref.removeprefix("refs/heads/"))
    return SelfCiPlan(
      "issue",
      issue,
      issue_verification_groups(root, issue),
      f"issue {issue} verification plus durable high-risk associations",
    )

  return SelfCiPlan(
    "integration",
    None,
    (),
    "fail-safe full integration for unclassified invocation",
  )


def _substitute(template: str, target: str, delim: str | None) -> str:
  if "$file" in template:
    raise SelfCiError("$file test-catalogue execution is not implemented")
  if "$tests" in template:
    if delim is None:
      raise SelfCiError("$tests requires a harness delimiter")
    template = template.replace("$tests", target)
  match = re.search(r"\$ftests\{([^{}]*\$test[^{}]*)\}", template)
  if match is not None:
    if delim is None:
      raise SelfCiError("$ftests requires a harness delimiter")
    template = template[:match.start()] + match.group(1).replace(
      "$test",
      target,
    ) + template[match.end():]
  return template.replace("$test", target)


def group_command(root: Path, group: str) -> tuple[str, ...]:
  records = _group_records(root)
  try:
    declaration, metadata = records[group]
  except KeyError as error:
    raise SelfCiError(f"unknown selected test group: {group}") from error

  harness_name = declaration["test-harness"]
  value = _catalogue_value(root)
  harness = value["test-harnesses"][harness_name]
  declaration_command = declaration.get("command")
  harness_command = harness.get("command")
  commands = [
    command
    for command in (declaration_command, harness_command)
    if command is not None
  ]
  if len(commands) != 1 or not isinstance(commands[0], str):
    raise SelfCiError(
      f"group {group} must resolve exactly one string command"
    )
  target = metadata.get("name")
  if not isinstance(target, str) or not target:
    raise SelfCiError(f"group {group} must define a native test name")
  layout = harness.get("layout")
  if isinstance(layout, str):
    layout = [layout]
  if not isinstance(layout, list) or not all(isinstance(x, str) for x in layout):
    raise SelfCiError(f"harness {harness_name} must define a string layout")
  leading = harness.get("leading-params", [])
  if not isinstance(leading, list) or not all(isinstance(x, str) for x in leading):
    raise SelfCiError(f"harness {harness_name} has invalid leading-params")
  delim = harness.get("delim")
  if delim is not None and not isinstance(delim, str):
    raise SelfCiError(f"harness {harness_name} has invalid delimiter")

  command = sys.executable if commands[0] == "python" else commands[0]
  args = [
    _substitute(item, target, delim)
    for item in [*leading, *layout]
  ]
  return tuple([command, *args])
