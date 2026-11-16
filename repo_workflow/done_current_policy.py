"""Read the current destination's allow-list on both admission checks."""
from .integration_admission import AdmissionError, decide_admission
from .prelim_queue import ReadyPrelim


class CurrentPolicyError(RuntimeError):
  """Provider could not establish the destination's current policy."""


def bind_current_policy(host, ready: ReadyPrelim, resolve_parent):
  if (not isinstance(ready, ReadyPrelim)
      or not callable(resolve_parent)
      or not callable(getattr(host, "request", None))):
    raise CurrentPolicyError("trusted destination policy interfaces required")
  generation = 0

  def admit(plan):
    nonlocal generation
    generation += 1
    key = ("policy-" + ready.guid + "-" + str(generation))
    try:
      facts = host.request("destination.read", key, {
        "destination": ready.destination})
    except Exception as error:
      raise CurrentPolicyError("authoritative destination UNKNOWN") from error
    if (type(facts) is not dict
        or set(facts) != {
          "destination", "ref", "sha", "policy_present", "policy_text"}
        or facts["destination"] != ready.destination
        or facts["ref"] != "refs/heads/" + ready.destination
        or type(facts["sha"]) is not str
        or type(facts["policy_present"]) is not bool
        or (facts["policy_present"] and type(facts["policy_text"]) is not str)
        or (not facts["policy_present"] and facts["policy_text"] is not None)):
      raise CurrentPolicyError("malformed authoritative destination readback")
    if facts["sha"] != plan.expected_parent_sha:
      raise CurrentPolicyError("destination advanced before admission")
    from .ticket_admission import policy_path
    path = policy_path(ready.destination).as_posix()

    def policy_reader(sha, requested):
      if sha != facts["sha"] or requested != path:
        raise CurrentPolicyError("destination policy path/source differs")
      return facts["policy_text"] if facts["policy_present"] else None

    try:
      return decide_admission(
        ready, facts["sha"], resolve_parent=resolve_parent,
        read_policy=policy_reader)
    except AdmissionError as error:
      raise CurrentPolicyError("destination policy or parent invalid") from error

  return admit
