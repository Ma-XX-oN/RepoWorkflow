"""Independent Git-backed readback of canonical #583 lifecycle records.

The caller designates the authoritative state branch. This adapter only
reads that branch; it never creates a competing lifecycle authority or
claims that an uncommitted local LifecycleStore is shared.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
import re

from .done_completion import VerifiedCompletion
from .lifecycle_store import LifecycleStore


_SHA=re.compile(r"[0-9a-f]{40}\Z")
_BRANCH=re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


class SharedLifecycleError(RuntimeError):
  """Remote canonical state cannot be proved at an unchanged Git ref."""


@dataclass(frozen=True)
class SharedLifecycleEvidence:
  repository: str
  branch: str
  commit_sha: str
  issue: int
  revision: int
  operation_id: str
  accepted_sha: str
  landed_sha: str
  lifecycle_digest: str
  intent_digest: str
  independently_authenticated: bool


def _sha(value):
  return type(value) is str and _SHA.fullmatch(value) is not None


def _git_blob(backend, commit, path):
  """Read an exact Git blob through immutable commit/tree SHA addresses."""
  if not _sha(commit):
    raise SharedLifecycleError("shared lifecycle commit SHA invalid")
  item=backend.get("git/commits/"+commit)
  tree=item.get("tree",{}).get("sha") if isinstance(item,dict) else None
  if not _sha(tree):
    raise SharedLifecycleError("remote lifecycle commit tree invalid")
  segments=path.split("/")
  for index,segment in enumerate(segments):
    observed=backend.get("git/trees/"+tree)
    entries=observed.get("tree") if isinstance(observed,dict) else None
    matches=[x for x in entries if type(x) is dict
             and x.get("path")==segment] if isinstance(entries,list) else []
    if len(matches)!=1 or not _sha(matches[0].get("sha")):
      raise SharedLifecycleError("canonical lifecycle path absent in remote")
    node=matches[0]
    if index<len(segments)-1:
      if node.get("type")!="tree":
        raise SharedLifecycleError("remote lifecycle path is not a tree")
      tree=node["sha"]
    else:
      if node.get("type")!="blob":
        raise SharedLifecycleError("remote lifecycle record is not a blob")
      blob=backend.get("git/blobs/"+node["sha"])
      if (not isinstance(blob,dict)
          or blob.get("encoding")!="base64"
          or type(blob.get("content")) is not str):
        raise SharedLifecycleError("provider blob encoding unknown")
      try:
        raw=base64.b64decode(blob["content"],validate=False)
        if hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()!=node["sha"]:
          raise ValueError("blob SHA differs")
        data=json.loads(raw.decode("utf-8"))
      except (ValueError,UnicodeError) as error:
        raise SharedLifecycleError("remote lifecycle blob invalid") from error
      if type(data) is not dict:
        raise SharedLifecycleError("remote canonical record not an object")
      return data
  raise SharedLifecycleError("unreachable canonical path")


def _digest(record):
  data=json.dumps(record,sort_keys=True,separators=(",",":"),
                  allow_nan=False).encode("utf-8")
  return hashlib.sha256(data).hexdigest()


def verify_shared_completion(*, backend, state_branch, local_store,
                             issue, completion):
  """Demand provider-persisted exact #583 records before native DONE."""
  if (not isinstance(local_store,LifecycleStore)
      or not isinstance(completion,VerifiedCompletion)
      or type(issue) is not int or issue<1
      or type(state_branch) is not str
      or _BRANCH.fullmatch(state_branch) is None
      or state_branch.startswith("/") or ".." in state_branch
      or getattr(backend,"repository",None) is None):
    raise SharedLifecycleError("trusted shared lifecycle provider required")
  intent_key="issues/"+str(issue)+"/done-intent"
  lifecycle_key="issues/"+str(issue)+"/lifecycle"
  try:
    local_lifecycle=local_store.records.read(lifecycle_key)
    local_intent=local_store.records.read(intent_key)
    snapshot=local_store.read(issue)
  except Exception as error:
    raise SharedLifecycleError("local canonical lifecycle read UNKNOWN") from error
  history=snapshot.lifecycle.history
  if (snapshot.lifecycle.state!="completed"
      or snapshot.lifecycle.dependency_satisfied is not True
      or snapshot.revision!=completion.lifecycle.get("revision")
      or snapshot.revision!=local_lifecycle.get("revision")
      or not history or history[-1].transition!="complete"
      or history[-1].candidate!=completion.terminal.accepted_sha
      or local_intent.get("revision")!=0
      or local_intent.get("value",{}).get("issue")!=str(issue)
      or local_intent.get("value",{}).get("operation_id")
         !=completion.operation_id
      or local_intent.get("value",{}).get("accepted_sha")
         !=completion.terminal.accepted_sha
      or local_intent.get("value",{}).get("landed_sha")
         !=completion.landed_sha):
    raise SharedLifecycleError("local authoritative completion identity differs")
  ref="refs/heads/"+state_branch
  try:
    first=backend.get("git/ref/heads/"+state_branch)
    if (type(first) is not dict or first.get("ref")!=ref
        or not _sha(first.get("object",{}).get("sha"))):
      raise SharedLifecycleError("remote state branch is not authoritative")
    commit=first["object"]["sha"]
    prefix=".repoworkflow/state/issues/"+str(issue)+"/"
    remote_lifecycle=_git_blob(backend,commit,prefix+"lifecycle.json")
    remote_intent=_git_blob(backend,commit,prefix+"done-intent.json")
    second=backend.get("git/ref/heads/"+state_branch)
  except SharedLifecycleError:
    raise
  except Exception as error:
    raise SharedLifecycleError("remote canonical readback UNKNOWN") from error
  if (remote_lifecycle!=local_lifecycle or remote_intent!=local_intent
      or second!=first):
    raise SharedLifecycleError(
      "remote canonical state differs or changed during readback")
  return SharedLifecycleEvidence(
    backend.repository,state_branch,commit,issue,snapshot.revision,
    completion.operation_id,completion.terminal.accepted_sha,
    completion.landed_sha,_digest(remote_lifecycle),_digest(remote_intent),
    True)


def publish_shared_completion(*, backend, state_branch, expected_old_commit,
                              local_store, issue, completion):
  """CAS-publish existing #583 records on an already authorised state ref.

  The existing remote lifecycle must be accepted at exactly revision N-1.
  A loss of the Git ref-update acknowledgment is recovered only by an exact
  independent reread of both canonical records, never by force or rollback.
  """
  if not _sha(expected_old_commit):
    raise SharedLifecycleError("expected old authoritative commit required")
  kwargs=dict(
    backend=backend,state_branch=state_branch,local_store=local_store,
    issue=issue,completion=completion)
  try:
    # An exact already-published result is an idempotent retry, not a write.
    return verify_shared_completion(**kwargs)
  except SharedLifecycleError:
    pass
  if (not isinstance(local_store,LifecycleStore)
      or not isinstance(completion,VerifiedCompletion)
      or type(issue) is not int or issue<1
      or type(state_branch) is not str
      or _BRANCH.fullmatch(state_branch) is None
      or ".." in state_branch):
    raise SharedLifecycleError("trusted lifecycle publication scope required")
  ref="refs/heads/"+state_branch
  prefix=".repoworkflow/state/issues/"+str(issue)+"/"
  try:
    remote=backend.get("git/ref/heads/"+state_branch)
    if (type(remote) is not dict or remote.get("ref")!=ref
        or remote.get("object",{}).get("sha")!=expected_old_commit):
      raise SharedLifecycleError("stale authoritative lifecycle ref")
    previous=_git_blob(
      backend,expected_old_commit,prefix+"lifecycle.json")
    current=local_store.records.read("issues/"+str(issue)+"/lifecycle")
    intent=local_store.records.read("issues/"+str(issue)+"/done-intent")
    before=previous.get("value",{})
    after=current.get("value",{})
    prior_history=before.get("history")
    next_history=after.get("history")
    if (previous.get("revision")!=completion.lifecycle.get("revision")-1
        or current.get("revision")!=completion.lifecycle.get("revision")
        or before.get("state")!="accepted"
        or after.get("state")!="completed"
        or before.get("issue")!=str(issue)
        or after.get("issue")!=str(issue)
        or before.get("relationship_revision")
           !=after.get("relationship_revision")
        or not isinstance(prior_history,list) or not prior_history
        or not isinstance(next_history,list)
        or next_history[:-1]!=prior_history
        or prior_history[-1].get("transition")!="accept"
        or prior_history[-1].get("candidate")
           !=completion.terminal.accepted_sha
        or next_history[-1].get("transition")!="complete"
        or next_history[-1].get("candidate")
           !=completion.terminal.accepted_sha
        or intent.get("revision")!=0
        or intent.get("value",{}).get("operation_id")
           !=completion.operation_id
        or intent.get("value",{}).get("landed_sha")
           !=completion.landed_sha):
      raise SharedLifecycleError(
        "accepted remote lifecycle is not exact predecessor")
    original=backend.get("git/commits/"+expected_old_commit)
    oldtree=original.get("tree",{}).get("sha")
    if not _sha(oldtree):
      raise SharedLifecycleError("old lifecycle tree malformed")
    tree=backend.post("git/trees",{
      "base_tree":oldtree,
      "tree":[{
        "path":prefix+name+".json",
        "mode":"100644","type":"blob",
        "content":json.dumps(data,indent=2,sort_keys=True)+"\n",
      } for name,data in (
        ("lifecycle",current),("done-intent",intent))]})
    if not _sha(tree.get("sha")):
      raise SharedLifecycleError("created lifecycle tree invalid")
    made=backend.post("git/commits",{
      "message":"RWF-CANONICAL-LIFECYCLE-V1 issue "+str(issue),
      "tree":tree["sha"],"parents":[expected_old_commit]})
    if not _sha(made.get("sha")):
      raise SharedLifecycleError("created lifecycle commit invalid")
    proposed=made["sha"]
  except SharedLifecycleError:
    raise
  except Exception as error:
    raise SharedLifecycleError("shared lifecycle publication preparation UNKNOWN") from error
  try:
    backend.patch(
      "git/refs/heads/"+state_branch,{"sha":proposed,"force":False})
  except Exception as error:
    # A failed CAS and a committed write with lost ACK have the same
    # transport symptom. Only exact remote bytes can resolve the ambiguity.
    try:
      return verify_shared_completion(**kwargs)
    except Exception as read_error:
      raise SharedLifecycleError(
        "shared lifecycle Git CAS UNKNOWN; do not retry blindly") from error
  proof=verify_shared_completion(**kwargs)
  if proof.commit_sha!=proposed:
    raise SharedLifecycleError("unexpected canonical lifecycle commit")
  return proof
