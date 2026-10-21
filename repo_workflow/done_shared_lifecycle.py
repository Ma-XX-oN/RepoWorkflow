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
