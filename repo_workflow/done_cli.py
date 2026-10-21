"""Native rwf done request boundary, distinct from read-only #108 plan.

A command is never a merge permit. The caller must supply a trusted,
provider-bound executor that returns the independently verified terminal,
retirement, promotion and lifecycle result, not an asserted PASS boolean.
"""
import json

from .done_completion import VerifiedCompletion
from .done_runtime import VerifiedDeferredDone,VerifiedFailedDone


class DoneCommandError(ValueError):
  """No verified executor or legal integration result is available."""


def execute_done_command(release, *, trusted_executor, emit):
  """Dispatch patch/minor/major only to an authenticated provider executor."""
  if release not in {"patch","minor","major"} or type(release) is not str:
    raise DoneCommandError("done requires patch, minor, or major")
  if not callable(trusted_executor) or not callable(emit):
    raise DoneCommandError("independent done execution authority is unavailable")
  try:
    outcome=trusted_executor(release)
  except Exception as error:
    raise DoneCommandError(
      "done provider outcome UNKNOWN; readback required") from error
  if isinstance(outcome,VerifiedCompletion):
    terminal=outcome.terminal
    proof=outcome.promotion
    lifecycle=outcome.lifecycle
    if (proof.operation_id != outcome.operation_id
        or proof.landed_sha != outcome.landed_sha
        or proof.accepted_candidate_sha != terminal.accepted_sha
        or terminal.operation_id != outcome.operation_id
        or terminal.landed_sha != outcome.landed_sha
        or len(outcome.retired)!=2
        or any(getattr(r,"absent_after",None) is not True
               for r in outcome.retired)
        or type(lifecycle) is not dict
        or lifecycle.get("result")!="done"
        or lifecycle.get("operation_id")!=outcome.operation_id
        or lifecycle.get("landed_sha")!=outcome.landed_sha
        or type(lifecycle.get("revision")) is not int
        or lifecycle["revision"]<1):
      raise DoneCommandError("provider completed result is not certified")
    emit(json.dumps({
      "status":"DONE","release":release,
      "landed_sha":outcome.landed_sha,
      "operation_id":outcome.operation_id,
      "evidence":"source-tested-accepted-at-destination",
    },sort_keys=True))
    return 0
  if isinstance(outcome,VerifiedDeferredDone):
    event=outcome.provider_event
    outcome=outcome.attempt
    if (getattr(event,"guid",None)!=outcome.ready.guid
        or getattr(event,"prelim_sha",None)!=outcome.ready.sha
        or getattr(event,"evidence_ref",None)!=outcome.evidence_ref
        or type(getattr(event,"lease_generation",None)) is not int
        or event.lease_generation+1!=outcome.released_generation):
      raise DoneCommandError("MIT deferred provider evidence differs")
    if (outcome.ready.guid
        and type(outcome.evidence_ref) is str
        and outcome.evidence_ref.strip()
        and type(outcome.released_generation) is int
        and outcome.released_generation>0):
      emit(json.dumps({
        "status":"MIT_TIMEOUT_DEFERRED","release":release,
        "guid":outcome.ready.guid,
        "evidence_ref":outcome.evidence_ref,
      },sort_keys=True))
      return 3
    raise DoneCommandError("MIT defer readback is incomplete")
  if isinstance(outcome,VerifiedFailedDone):
    handoff=outcome.persisted_handoff
    outcome=outcome.attempt
    if (handoff.handoff.guid!=outcome.ready.guid
        or handoff.handoff.prelim_sha!=outcome.ready.sha
        or handoff.handoff.failure_kind!=outcome.failed_stage+"_FAIL"
        or not handoff.per_issue_refs):
      raise DoneCommandError("durable owner handoff differs")
    if (outcome.ready.guid
        and outcome.failed_stage in {"ART","AIT","release","MIT"}
        and type(outcome.evidence_ref) is str
        and outcome.evidence_ref.strip()
        and type(outcome.released_generation) is int
        and outcome.released_generation>0):
      emit(json.dumps({
        "status":"FAILED_STAGE","release":release,
        "guid":outcome.ready.guid,
        "stage":outcome.failed_stage,
        "evidence_ref":outcome.evidence_ref,
      },sort_keys=True))
      return 4
    raise DoneCommandError("failed-stage terminal unverified")
  raise DoneCommandError("unverified done outcome; no success claim permitted")
