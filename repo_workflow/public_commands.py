from __future__ import annotations

from .command_grammar import Context, validate_node
from .workflow_state import derive_plan, discover_facts


def _plan(context: Context):
  return derive_plan(discover_facts(context.root))


def _integration_results(context: Context) -> list[dict]:
  descriptions = {
    "succeeded": "Report integration tests succeeded",
    "failed": "Report integration tests failed",
  }
  if not context.legal_only:
    names = ("failed", "succeeded")
  else:
    allowed = set(_plan(context).transitions)
    names = tuple(
      name
      for name in ("failed", "succeeded")
      if f"validate integration {name}" in allowed
    )
  return [{name: descriptions[name]} for name in names]


def _integration_node() -> dict:
  return {
    "_values": _integration_results,
  }


def _regression_node() -> dict:
  return {
    "": "Run all regression tests",
  }


def _validate_commands(context: Context) -> list[dict]:
  if not context.legal_only:
    return [
      {"regression": _regression_node()},
      {"integration": _integration_node()},
    ]

  transitions = _plan(context).transitions
  fragments: list[dict] = []
  if "validate regression" in transitions:
    fragments.append({"regression": _regression_node()})
  if any(item.startswith("validate integration ") for item in transitions):
    fragments.append({"integration": _integration_node()})
  return fragments


def _issue_number(context: Context) -> list[str]:
  token = context.current_token
  if token and token.isdecimal():
    return [token]
  return []


COMMANDS = {
  "what-next": {
    "": "Show legal next workflow transitions",
    "--json": "Output workflow guidance as JSON",
  },
  "validate": {
    "_values": _validate_commands,
  },
  "version": {
    "": "Show the repository version",
    "--json": "Output the repository version as JSON",
    "task": {
      "issue": {
        "_values": _issue_number,
      },
    },
    "integrate": {
      "increment": {
        "patch": "Request a patch integration version",
        "minor": "Request a minor integration version",
      },
    },
    "release-major": "Request the next major release version",
  },
}


validate_node(COMMANDS)


PUBLIC_COMMANDS = frozenset(COMMANDS)
