"""Stream grammar and incremental JSON-array I/O for interface playback."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any, Iterator


class InterfaceGrammarError(ValueError):
  """Raised when a recording does not satisfy the interface grammar."""


_ALLOWED_META = {"$new", "$ref", "$type", "$free", "$unchanged"}


def _type_name(value: type) -> str:
  return f"{value.__module__}.{value.__qualname__}"


def normalize_python(value: Any) -> Any:
  """Convert public Python conveniences to the canonical JSON grammar."""
  from .interface_playback import Free, Unchanged

  if value is Free:
    return {"$free": True}
  if value is Unchanged:
    return {"$unchanged": True}
  if isinstance(value, Unchanged):
    if value.keys is None:
      return {"$unchanged": True}
    return {"$unchanged": {"keys": list(value.keys)}}
  if isinstance(value, list):
    return [normalize_python(item) for item in value]
  if isinstance(value, dict):
    result = {}
    for key, item in value.items():
      if key == "$type" and isinstance(item, type):
        result[key] = _type_name(item)
      else:
        result[key] = normalize_python(item)
    return result
  if isinstance(value, tuple):
    raise InterfaceGrammarError(
      "tuple is not streamable without an explicit grammar representation"
    )
  if isinstance(value, type):
    raise InterfaceGrammarError(
      "live Python type is only permitted as the value of $type"
    )
  return deepcopy(value)


def _validate_json_scalar(value: Any, path: str) -> None:
  if value is None or isinstance(value, (bool, str, int)):
    return
  if isinstance(value, float):
    if not math.isfinite(value):
      raise InterfaceGrammarError(f"{path}: non-finite float is not valid")
    return
  raise InterfaceGrammarError(
    f"{path}: unsupported value type {type(value).__name__}"
  )


def _validate_unchanged(value: Any, path: str) -> None:
  if value is True:
    return
  if not isinstance(value, dict) or set(value) != {"keys"}:
    raise InterfaceGrammarError(
      f'{path}.$unchanged: expected true or {{"keys": [...]}}'
    )
  keys = value["keys"]
  if not isinstance(keys, list) or not keys:
    raise InterfaceGrammarError(
      f"{path}.$unchanged.keys: expected non-empty list"
    )
  if any(not isinstance(key, str) or not key for key in keys):
    raise InterfaceGrammarError(
      f"{path}.$unchanged.keys: keys must be non-empty strings"
    )
  if len(set(keys)) != len(keys):
    raise InterfaceGrammarError(
      f"{path}.$unchanged.keys: duplicate keys are not allowed"
    )


def validate_value(value: Any, path: str = "$") -> None:
  if isinstance(value, list):
    for index, item in enumerate(value):
      validate_value(item, f"{path}[{index}]")
    return
  if not isinstance(value, dict):
    _validate_json_scalar(value, path)
    return

  dollar = {
    key
    for key in value
    if isinstance(key, str) and key.startswith("$")
  }
  unknown = dollar - _ALLOWED_META
  if unknown:
    name = sorted(unknown)[0]
    raise InterfaceGrammarError(f"{path}: unknown reserved key {name}")
  if any(not isinstance(key, str) for key in value):
    raise InterfaceGrammarError(f"{path}: mapping keys must be strings")

  if "$free" in value:
    if value != {"$free": True}:
      raise InterfaceGrammarError(f"{path}: $free must be exactly true")
    return
  if "$unchanged" in value:
    if set(value) != {"$unchanged"}:
      raise InterfaceGrammarError(
        f"{path}: $unchanged cannot be combined with other fields"
      )
    _validate_unchanged(value["$unchanged"], path)
    return
  if "$new" in value and "$ref" in value:
    raise InterfaceGrammarError(f"{path}: $new and $ref are mutually exclusive")
  for key in ("$new", "$ref"):
    if key in value and (
      not isinstance(value[key], str) or not value[key]
    ):
      raise InterfaceGrammarError(f"{path}.{key}: expected non-empty string")
  if "$type" in value and (
    not isinstance(value["$type"], str) or "." not in value["$type"]
  ):
    raise InterfaceGrammarError(
      f"{path}.$type: expected stable module-qualified type string"
    )

  for key, item in value.items():
    if not key.startswith("$"):
      validate_value(item, f"{path}.{key}")


def validate_interaction(interaction: Any, index: int | None = None) -> None:
  prefix = f"interaction {index}" if index is not None else "interaction"
  if not isinstance(interaction, dict):
    raise InterfaceGrammarError(f"{prefix}: expected object")
  if set(interaction) != {"call", "before", "after", "result"}:
    raise InterfaceGrammarError(
      f"{prefix}: expected call, before, after, and result"
    )

  call = interaction["call"]
  if not isinstance(call, dict) or set(call) != {"fn_name", "obj"}:
    raise InterfaceGrammarError(
      f"{prefix}.call: expected fn_name and obj"
    )
  if not isinstance(call["fn_name"], str) or not call["fn_name"]:
    raise InterfaceGrammarError(
      f"{prefix}.call.fn_name: expected non-empty string"
    )
  validate_value(call["obj"], f"{prefix}.call.obj")
  free = call["obj"] == {"$free": True}

  for phase in ("before", "after"):
    state = interaction[phase]
    if not isinstance(state, dict):
      raise InterfaceGrammarError(f"{prefix}.{phase}: expected object")
    required = {"args", "kwargs"} if free else {"obj", "args", "kwargs"}
    if set(state) != required:
      raise InterfaceGrammarError(
        f"{prefix}.{phase}: expected fields {sorted(required)}"
      )
    if not isinstance(state["args"], list):
      raise InterfaceGrammarError(f"{prefix}.{phase}.args: expected list")
    if not isinstance(state["kwargs"], dict):
      raise InterfaceGrammarError(f"{prefix}.{phase}.kwargs: expected object")
    for key in state["kwargs"]:
      if not isinstance(key, str):
        raise InterfaceGrammarError(
          f"{prefix}.{phase}.kwargs: keys must be strings"
        )
    if not free:
      validate_value(state["obj"], f"{prefix}.{phase}.obj")
    validate_value(state["args"], f"{prefix}.{phase}.args")
    validate_value(state["kwargs"], f"{prefix}.{phase}.kwargs")

  result = interaction["result"]
  if not isinstance(result, dict) or len(result) != 1:
    raise InterfaceGrammarError(
      f"{prefix}.result: expected exactly one of return or raise"
    )
  if "return" in result:
    validate_value(result["return"], f"{prefix}.result.return")
  elif "raise" in result:
    raised = result["raise"]
    if not isinstance(raised, dict) or set(raised) != {"$type", "args"}:
      raise InterfaceGrammarError(
        f"{prefix}.result.raise: expected $type and args"
      )
    validate_value(raised, f"{prefix}.result.raise")
    if not isinstance(raised["args"], list):
      raise InterfaceGrammarError(
        f"{prefix}.result.raise.args: expected list"
      )
  else:
    raise InterfaceGrammarError(
      f"{prefix}.result: expected exactly one of return or raise"
    )


def validate_reference_order(
  interaction: dict[str, Any],
  bound: set[str],
  index: int,
) -> None:
  """Validate logical-reference ordering in one syntax-checked interaction."""

  def walk(value: Any, path: str) -> None:
    if isinstance(value, list):
      for item_index, item in enumerate(value):
        walk(item, f"{path}[{item_index}]")
      return
    if not isinstance(value, dict):
      return
    if "$free" in value or "$unchanged" in value:
      return
    if "$new" in value:
      name = value["$new"]
      if name in bound:
        raise InterfaceGrammarError(
          f"{path}: duplicate logical object introduction {name!r}"
        )
      bound.add(name)
    elif "$ref" in value:
      name = value["$ref"]
      if name not in bound:
        raise InterfaceGrammarError(
          f"{path}: forward or unknown logical object reference {name!r}"
        )
    for key, item in value.items():
      if not key.startswith("$"):
        walk(item, f"{path}.{key}")

  prefix = f"interaction {index}"
  walk(interaction["call"]["obj"], f"{prefix}.call.obj")
  before = interaction["before"]
  if "obj" in before:
    walk(before["obj"], f"{prefix}.before.obj")
  walk(before["args"], f"{prefix}.before.args")
  walk(before["kwargs"], f"{prefix}.before.kwargs")
  after = interaction["after"]
  if "obj" in after:
    walk(after["obj"], f"{prefix}.after.obj")
  walk(after["args"], f"{prefix}.after.args")
  walk(after["kwargs"], f"{prefix}.after.kwargs")
  result = interaction["result"]
  if "return" in result:
    walk(result["return"], f"{prefix}.result.return")
  else:
    walk(result["raise"]["args"], f"{prefix}.result.raise.args")


def validate_interactions(
  interactions: Iterator[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
  """Validate syntax and logical-reference ordering while streaming."""
  bound: set[str] = set()
  for index, interaction in enumerate(interactions):
    validate_interaction(interaction, index)
    validate_reference_order(interaction, bound, index)
    yield interaction


def validate_recording(recording: Any) -> list[dict[str, Any]]:
  normalized = normalize_python(recording)
  if not isinstance(normalized, list):
    raise InterfaceGrammarError("recording: expected list of interactions")
  bound: set[str] = set()
  for index, interaction in enumerate(normalized):
    validate_interaction(interaction, index)
    validate_reference_order(interaction, bound, index)
  return normalized


class JsonArrayReader:
  """Incrementally decode one top-level JSON array."""

  def __init__(self, path: str | Path, chunk_size: int = 65536):
    self.path = Path(path)
    self.chunk_size = chunk_size

  def __iter__(self) -> Iterator[dict[str, Any]]:
    decoder = json.JSONDecoder()
    with self.path.open("r", encoding="utf-8") as handle:
      buffer = ""
      position = 0
      started = False
      finished = False
      index = 0

      while True:
        if position >= len(buffer) and not finished:
          chunk = handle.read(self.chunk_size)
          if chunk:
            buffer = chunk
            position = 0
          else:
            finished = True

        while True:
          while position < len(buffer) and buffer[position].isspace():
            position += 1

          if not started:
            if position >= len(buffer):
              break
            if buffer[position] != "[":
              raise InterfaceGrammarError("recording: expected JSON array")
            position += 1
            started = True
            continue

          while position < len(buffer) and buffer[position].isspace():
            position += 1
          if position < len(buffer) and buffer[position] == "]":
            position += 1
            while position < len(buffer) and buffer[position].isspace():
              position += 1
            if position != len(buffer) or not finished:
              tail = buffer[position:] + handle.read()
              if tail.strip():
                raise InterfaceGrammarError(
                  "recording: trailing data after JSON array"
                )
            return

          if position >= len(buffer):
            break

          try:
            value, end = decoder.raw_decode(buffer, position)
          except json.JSONDecodeError:
            if finished:
              raise InterfaceGrammarError(
                "recording: malformed or truncated JSON"
              )
            remainder = buffer[position:]
            chunk = handle.read(self.chunk_size)
            if not chunk:
              finished = True
            buffer = remainder + chunk
            position = 0
            continue

          validate_interaction(value, index)
          yield value
          index += 1
          position = end

          while position < len(buffer) and buffer[position].isspace():
            position += 1
          if position >= len(buffer):
            break
          if buffer[position] == ",":
            position += 1
            continue
          if buffer[position] == "]":
            continue
          raise InterfaceGrammarError(
            f"interaction {index}: expected comma or closing bracket"
          )

        if finished:
          if not started:
            raise InterfaceGrammarError("recording: empty file")
          raise InterfaceGrammarError("recording: truncated JSON array")
        remainder = buffer[position:]
        chunk = handle.read(self.chunk_size)
        if not chunk:
          finished = True
        buffer = remainder + chunk
        position = 0


def write_json_array(
  path: str | Path,
  interactions: Iterator[dict[str, Any]],
) -> None:
  target = Path(path)
  with target.open("w", encoding="utf-8", newline="\n") as handle:
    handle.write("[\n")
    first = True
    for index, interaction in enumerate(interactions):
      validate_interaction(interaction, index)
      if not first:
        handle.write(",\n")
      json.dump(
        interaction,
        handle,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
      )
      first = False
    handle.write("\n]\n")
