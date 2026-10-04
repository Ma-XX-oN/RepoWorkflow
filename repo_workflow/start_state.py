from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .state_store import StateStoreError, durable_store
from .runtime_identity import runtime_writer_identity

STATES={"start","start-preliminary","start-failed","implement"}

class StartStateError(RuntimeError):
  pass

@dataclass(frozen=True)
class StartState:
  issue: int
  state: str
  detail: str | None = None

class StartStateStore:
  def __init__(self,root:Path):
    self.records=durable_store(Path(root).resolve())
  def read(self,issue:int)->StartState:
    try: record=self.records.read(f"issues/{issue}/start-state")
    except StateStoreError as error:
      if "record is missing:" in str(error): return StartState(issue,"start")
      raise StartStateError(str(error)) from error
    value=record["value"]
    if not isinstance(value,dict) or set(value)!={"issue","state","detail"} or value["issue"]!=issue or value["state"] not in STATES or (value["detail"] is not None and not isinstance(value["detail"],str)):
      raise StartStateError("invalid durable start state")
    return StartState(**value)
  def write(self,value:StartState)->StartState:
    if value.state not in STATES: raise StartStateError("invalid start state")
    key=f"issues/{value.issue}/start-state"; writer=runtime_writer_identity()
    try: current=self.records.read(key)
    except StateStoreError as error:
      if "record is missing:" not in str(error): raise StartStateError(str(error)) from error
      self.records.create(key,{"issue":value.issue,"state":value.state,"detail":value.detail},writer); return value
    self.records.replace(key,current["revision"],{"issue":value.issue,"state":value.state,"detail":value.detail},writer); return value
