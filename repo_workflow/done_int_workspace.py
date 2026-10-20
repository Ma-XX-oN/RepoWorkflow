"""Publish only the coordinator-owned mutable INT workspace via #681 v2.

PRELIM itself remains an immutable READY submission. This module creates
no queue branches and never considers a prepared INT sufficient to merge.
"""
from dataclasses import dataclass
import re

from .prelim_queue import ReadyPrelim


_SHA = re.compile(r"[0-9a-f]{40}\Z")


class IntPreparationError(RuntimeError):
  """Provider provenance, destination or prepared workspace is incomplete."""


@dataclass(frozen=True)
class PreparedIntWorkspace:
  prelim_ref: str
  prelim_sha: str
  int_ref: str
  accepted_sha: str
  expected_destination_sha: str
  create_id: str
  update_id: str


def publish_int_workspace(*, host, ready, expected_parent_sha, accepted_sha,
                          create_id, update_id):
  """Create INT from immutable PRELIM and CAS it to tested integration source.

  The caller must have separately reconstructed and independently certified
  accepted_sha against expected_parent_sha before invoking this function.
  """
  if not isinstance(ready, ReadyPrelim):
    raise IntPreparationError("authenticated READY identity required")
  if any(type(value) is not str or _SHA.fullmatch(value) is None
         for value in (ready.sha, expected_parent_sha, accepted_sha)):
    raise IntPreparationError("invalid pinned source or destination SHA")
  if (type(create_id) is not str or not create_id.strip()
      or type(update_id) is not str or not update_id.strip()
      or create_id == update_id
      or not callable(getattr(host, "request", None))):
    raise IntPreparationError("independent provider request identities required")
  int_ref = ready.ref.replace("refs/heads/PRELIM-",
                              "refs/heads/INT-ATTEMPT-", 1)
  if int_ref == ready.ref or not int_ref.startswith(
      "refs/heads/INT-ATTEMPT-"):
    raise IntPreparationError("incorrect integration workspace scope")

  def published_ready(phase):
    result = host.request("refs.list", create_id + "-inventory-" + phase, {
      "prefix": "refs/heads/PRELIM-"})
    if (type(result) is not dict
        or type(result.get("refs")) is not dict
        or result["refs"].get(ready.ref) != ready.sha):
      raise IntPreparationError("immutable READY ref changed or disappeared")

  def current_destination(phase):
    record = host.request("destination.read", update_id + "-destination-" + phase, {
      "destination": ready.destination})
    if (type(record) is not dict
        or record.get("ref") != "refs/heads/" + ready.destination
        or record.get("sha") != expected_parent_sha):
      raise IntPreparationError("destination moved during INT preparation")

  published_ready("before")
  current_destination("before")
  created = host.request("ref.create", create_id, {
    "ref": int_ref, "sha": ready.sha})
  if created != {"ref": int_ref, "sha": ready.sha}:
    raise IntPreparationError("INT initial source was not confirmed")
  if accepted_sha != ready.sha:
    updated = host.request("ref.cas", update_id, {
      "ref": int_ref, "expected_sha": ready.sha, "sha": accepted_sha})
    if updated != {"ref": int_ref, "sha": accepted_sha}:
      raise IntPreparationError("INT accepted source was not confirmed")
  published_ready("after")
  current_destination("after")
  return PreparedIntWorkspace(
    ready.ref, ready.sha, int_ref, accepted_sha, expected_parent_sha,
    create_id, update_id)
