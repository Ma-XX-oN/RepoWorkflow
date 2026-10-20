"""Terminal-to-retirement-to-evidence completion; never infer DONE.

Consume an accepted provider attempt and independently authenticated #103
retirement operation. Promotion and lifecycle writes require read-after-write.
This module neither changes protected main nor generates missing test PASS.
"""
from dataclasses import dataclass

from .done_executor import DoneExecutionError
from .done_provider_pipeline import AcceptedProviderAttempt
from .done_retirement_bridge import retirement_bridge_from_v2
from .done_evidence_promotion import Promotion
from .prelim_retirement_remote import RefRetirement


class CompletionError(DoneExecutionError):
  """Integrated-but-unretired or unevidenced is not DONE."""


@dataclass(frozen=True)
class VerifiedCompletion:
  operation_id: str
  landed_sha: str
  terminal: object
  retired: tuple[RefRetirement, RefRetirement]
  promotion: Promotion
  lifecycle: object


def complete_accepted_provider_attempt(
    *, host, accepted, retire_ref, promote, persist_lifecycle,
    read_lifecycle, retirement_id_prefix,
):
  """Reject partial completion even after successful destination integration.

  External adapters must independently authenticate physical ref retirement,
  source-tested evidence, immutable provider history and lifecycle revisions.
  An UNKNOWN write is reconciled by readback, never repeated blindly.
  """
  if (not isinstance(accepted, AcceptedProviderAttempt)
      or not callable(getattr(host, "request", None))
      or any(not callable(fn) for fn in (
        retire_ref,promote,persist_lifecycle,read_lifecycle))
      or type(retirement_id_prefix) is not str
      or not retirement_id_prefix.strip()):
    raise CompletionError("exact accepted provider state is required")
  terminal=accepted.terminal
  if (terminal.operation_id != accepted.accepted.operation_id
      or terminal.landed_sha != accepted.accepted.landed_sha
      or terminal.guid != accepted.ready.guid
      or terminal.repository != host.repository):
    raise CompletionError("terminal disagrees with accepted attempt")
  bridge=retirement_bridge_from_v2(host,terminal)
  landed=bridge.landed
  observed=[]
  for kind,ref,sha in (
      ("PRELIM",landed.prelim_ref,landed.prelim_sha),
      ("INT-ATTEMPT",landed.int_attempt_ref,landed.accepted_sha)):
    try:
      result=retire_ref(landed,bridge.read_terminal,kind)
    except Exception as error:
      raise CompletionError("physical retirement UNKNOWN") from error
    if (not isinstance(result,RefRetirement)
        or result.ref != ref
        or result.previously_observed_sha != sha
        or result.absent_after is not True):
      raise CompletionError("physical attempt retirement unverified")
    operation=retirement_id_prefix+"-"+kind
    record={
      "repository":host.repository,"guid":terminal.guid,
      "ref_kind":kind,"retired_ref":ref,"expected_sha":sha,
      "operation_id":operation,
      "terminal_evidence_ref":landed.terminal_evidence_ref,
      "destination_ref":landed.destination_ref,
      "landed_sha":landed.landed_sha,"outcome":"retired",
    }
    try:
      host.request("retirement.record",operation,{
        "guid":terminal.guid,"ref_kind":kind,"record":record})
    except Exception:
      pass
    try:
      remote=host.request("retirement.read",operation+"-read",{
        "guid":terminal.guid,"ref_kind":kind})
    except Exception as error:
      raise CompletionError("retirement readback UNKNOWN") from error
    if remote != {"guid":terminal.guid,"ref_kind":kind,"record":record}:
      raise CompletionError("durable retirement history absent or foreign")
    observed.append(result)
  try:
    proof=promote(accepted)
  except Exception as error:
    raise CompletionError("source-to-landed promotion UNKNOWN") from error
  if (not isinstance(proof,Promotion)
      or proof.operation_id != accepted.accepted.operation_id
      or proof.landed_sha != terminal.landed_sha
      or proof.accepted_candidate_sha != terminal.accepted_sha
      or proof.target_before_sha != terminal.record.get(
        'expected_destination_sha')
      or proof.tested_source_sha != terminal.accepted_sha):
    raise CompletionError("promotion provenance differs")
  try:
    persist_lifecycle(accepted,proof)
  except Exception:
    pass
  try:
    lifecycle=read_lifecycle(accepted)
  except Exception as error:
    raise CompletionError("lifecycle revision readback UNKNOWN") from error
  if (type(lifecycle) is not dict
      or lifecycle.get("guid") != terminal.guid
      or lifecycle.get("operation_id") != terminal.operation_id
      or lifecycle.get("landed_sha") != terminal.landed_sha
      or lifecycle.get("result") != "done"
      or type(lifecycle.get("revision")) is not int
      or lifecycle["revision"] < 1):
    raise CompletionError("durable DONE lifecycle history unverified")
  return VerifiedCompletion(
    terminal.operation_id,terminal.landed_sha,terminal,tuple(observed),
    proof,lifecycle)
