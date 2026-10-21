"""Append-only GitHub provider record of #109 landed-source promotion.

A promotion Git tag is independent evidence history, NEVER a new testing
PASS, release tag, queue branch or destination mutation. Caller must supply
independent current-landing and exact hosted-source evidence authorities.
"""
from dataclasses import asdict
import hashlib
import json
import re

from repo_workflow.done_evidence_promotion import (
  AuthenticatedStage, Promotion,
)


class DonePromotionProviderError(RuntimeError):
  """Immutable provider promotion cannot be proved."""


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_MESSAGE="RWF-DONE-PROMOTION-V1 "
_PREFIX="refs/tags/rwf-done-promotion-v1-"


def _canonical(value):
  return json.dumps(value,sort_keys=True,separators=(",",":"))


def _record(repo,destination,promotion):
  return {
    "schema_version":1,
    "repository":repo,
    "destination":destination,
    "promotion":asdict(promotion),
  }


def _ref(repository,destination,operation_id):
  if any(type(value) is not str or not value.strip()
         for value in (repository,destination,operation_id)):
    raise DonePromotionProviderError("exact promotion scope missing")
  identity=_canonical([repository,destination,operation_id])
  return _PREFIX+hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _validate(backend,destination,promotion):
  if (not isinstance(promotion,Promotion)
      or promotion.disposition != "source-tested-accepted-at-destination"
      or type(destination) is not str or not destination
      or any(type(v) is not str or _SHA.fullmatch(v) is None
             for v in (
               promotion.tested_source_sha,promotion.accepted_candidate_sha,
               promotion.target_before_sha,promotion.landed_sha,
               promotion.landed_tree_sha,promotion.source_tree_sha))
      or promotion.landed_tree_sha != promotion.source_tree_sha
      or type(promotion.stages) is not tuple
      or len(promotion.stages) != 3
      or {s.stage for s in promotion.stages
          if isinstance(s,AuthenticatedStage)}
         != {"regression","integration","release"}
      or any(not isinstance(s,AuthenticatedStage)
             or s.source_sha != promotion.tested_source_sha
             or s.status != "PASS" or s.authenticated is not True
             for s in promotion.stages)):
    raise DonePromotionProviderError("incomplete exact promotion evidence")
  return _ref(backend.repository,destination,promotion.operation_id)


def read_done_promotion(backend,destination,operation_id):
  """Resolve create-once history by exact provider Git ref and record."""
  ref=_ref(backend.repository,destination,operation_id)
  try:
    remote=backend.get("git/ref/tags/"+ref.rsplit("/",1)[1])
  except Exception as error:
    if getattr(error,"code",None)=="not_found":
      return None
    raise DonePromotionProviderError("provider promotion inventory UNKNOWN") from error
  if (type(remote) is not dict or remote.get("ref")!=ref
      or type(remote.get("object")) is not dict):
    raise DonePromotionProviderError("promotion Git ref malformed")
  commit=remote["object"].get("sha")
  if type(commit) is not str or _SHA.fullmatch(commit) is None:
    raise DonePromotionProviderError("promotion Git commit SHA malformed")
  try:
    message=backend.get("git/commits/"+commit)["message"]
    if not isinstance(message,str) or not message.startswith(_MESSAGE):
      raise ValueError("not a promotion commit")
    data=json.loads(message[len(_MESSAGE):])
  except (KeyError,ValueError,TypeError) as error:
    raise DonePromotionProviderError("promotion commit malformed") from error
  if _canonical(data)!=message[len(_MESSAGE):]:
    raise DonePromotionProviderError("promotion record not canonical")
  if (type(data) is not dict
      or set(data)!={"schema_version","repository","destination","promotion"}
      or data["schema_version"] != 1
      or data["repository"] != backend.repository
      or data["destination"] != destination
      or type(data["promotion"]) is not dict):
    raise DonePromotionProviderError("foreign promotion record")
  try:
    embedded=data["promotion"]
    stages=tuple(AuthenticatedStage(**s) for s in embedded["stages"])
    proof=Promotion(**{**embedded,"stages":stages})
  except (TypeError,KeyError,ValueError) as error:
    raise DonePromotionProviderError("promotion contents invalid") from error
  if proof.operation_id!=operation_id:
    raise DonePromotionProviderError("promotion operation identity differs")
  _validate(backend,destination,proof)
  return proof


def record_done_promotion(backend,destination,promotion,*,
                          verify_landing,verify_stages):
  """Create-once append-only attestation after fresh external proof."""
  ref=_validate(backend,destination,promotion)
  if not callable(verify_landing) or not callable(verify_stages):
    raise DonePromotionProviderError("independent provider verifiers required")
  current=backend.get("git/ref/heads/"+destination)
  if (current.get("ref")!="refs/heads/"+destination
      or current.get("object",{}).get("sha")!=promotion.landed_sha):
    raise DonePromotionProviderError("landed target no longer current")
  if (verify_landing(promotion,destination) is not True
      or verify_stages(promotion) is not True):
    raise DonePromotionProviderError("source and landing not independently verified")
  previous=read_done_promotion(backend,destination,promotion.operation_id)
  if previous is not None:
    if previous!=promotion:
      raise DonePromotionProviderError("immutable operation already has foreign record")
    return previous
  commit=backend.get("git/commits/"+promotion.landed_sha)
  tree=commit.get("tree",{}).get("sha")
  if tree!=promotion.landed_tree_sha:
    raise DonePromotionProviderError("landed tree no longer equivalent")
  body=_MESSAGE+_canonical(_record(backend.repository,destination,promotion))
  try:
    made=backend.post("git/commits",{
      "message":body,"tree":tree,"parents":[promotion.landed_sha]})
    if type(made.get("sha")) is not str or _SHA.fullmatch(made["sha"]) is None:
      raise ValueError("created promotion commit SHA invalid")
    backend.post("git/refs",{"ref":ref,"sha":made["sha"]})
  except Exception as error:
    # Do not duplicate a committed attestation after an ambiguous ACK.
    if read_done_promotion(backend,destination,promotion.operation_id)==promotion:
      return promotion
    raise DonePromotionProviderError("promotion append UNKNOWN") from error
  observed=read_done_promotion(backend,destination,promotion.operation_id)
  if observed!=promotion:
    raise DonePromotionProviderError("promotion readback differs after append")
  final=backend.get("git/ref/heads/"+destination)
  if final.get("object",{}).get("sha")!=promotion.landed_sha:
    raise DonePromotionProviderError("destination advanced during promotion")
  return observed
