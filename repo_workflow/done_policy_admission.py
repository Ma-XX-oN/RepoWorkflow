"""Destination-local immediate-child admission, not a PRELIM policy snapshot.

The authenticated provider reads the destination's current SHA and allow-list.
A separate authoritative relationship oracle must verify immediate parenthood.
"""
from dataclasses import dataclass
import re
from uuid import uuid4

from .done_planner import DonePlan
from .integration_admission import AdmissionDecision


class DestinationPolicyError(RuntimeError):
  """Destination policy could not be independently established."""


_DECIMAL = re.compile(r"[1-9][0-9]*$")


def _allowed_tickets(text):
  if not isinstance(text, str):
    raise DestinationPolicyError("present destination policy lacks text")
  if text == "":
    return frozenset()
  entries = text.splitlines()
  if any(_DECIMAL.fullmatch(v) is None for v in entries):
    raise DestinationPolicyError("policy is not one decimal issue per line")
  if len(entries) != len(set(entries)):
    raise DestinationPolicyError("duplicate issue numbers in allow-list")
  return frozenset(entries)


def current_destination_admission(host, plan, is_immediate_child):
  """Return a strict admission observation bound to the provider target SHA."""
  if (not isinstance(plan, DonePlan)
      or not callable(is_immediate_child)
      or not callable(getattr(host, "request", None))
      or _DECIMAL.fullmatch(plan.issue) is None):
    raise DestinationPolicyError("plan or relationship oracle unverified")
  observation = host.request("destination.read",
    "policy-" + plan.issue + "-" + uuid4().hex, {
      "destination":plan.target})
  if (type(observation) is not dict
      or set(observation) != {
        "destination","ref","sha","policy_present","policy_text"}
      or observation["destination"] != plan.target
      or observation["ref"] != "refs/heads/" + plan.target
      or type(observation["policy_present"]) is not bool):
    raise DestinationPolicyError("provider destination observation invalid")
  if observation["sha"] != plan.expected_parent_sha:
    return AdmissionDecision(
      int(plan.issue),plan.target,observation["sha"],False,"stale parent")
  present=observation["policy_present"]
  if present:
    permitted=_allowed_tickets(observation["policy_text"])
    if plan.issue not in permitted:
      return AdmissionDecision(
        int(plan.issue),plan.target,observation["sha"],False,
        "not explicitly allowed")
  elif observation["policy_text"] is not None:
    raise DestinationPolicyError("absent policy must have null contents")
  try:
    direct=is_immediate_child(plan.issue,plan.target)
  except Exception as error:
    raise DestinationPolicyError("relationship oracle UNKNOWN") from error
  if type(direct) is not bool:
    raise DestinationPolicyError("relationship oracle lacks verified verdict")
  return AdmissionDecision(
    int(plan.issue),plan.target,observation["sha"],direct,
    "immediate parent confirmed" if direct else "non-immediate parent")
