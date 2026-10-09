"""Reusable executable-interface recording, replay, and verification."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterable

from ._grammar import (
  InterfaceGrammarError,
  JsonArrayReader,
  normalize_python,
  validate_interaction,
  validate_interactions,
  validate_recording,
  validate_reference_order,
  write_json_array,
)
from ._values import InterfaceMismatch, ValueEngine, resolve_type, type_name


class Free:
  """Sentinel class identifying a free-function interaction."""


class Unchanged:
  """Declarative before/after equality requirement."""

  def __init__(self, *, keys: Iterable[str] | None = None):
    self.keys = None if keys is None else tuple(keys)


class InterfacePlayback:
  """Record, replay, and test ordered executable-interface interactions."""

  def __init__(self, source: Any | None = None):
    self._recording: list[dict[str, Any]] = []
    self._loaded_path: Path | None = None
    self._reader = None
    self._cursor = 0
    self._pending: dict[str, Any] | None = None
    self._values = ValueEngine()
    self._record_bound: set[str] = set()
    if source is not None:
      self.load(source)

  def load(self, source: Any) -> "InterfacePlayback":
    """Load a recording structure or a streamable JSON recording file."""
    self._reset_runtime()
    if isinstance(source, (str, Path)):
      path = Path(source)
      for _ in validate_interactions(iter(JsonArrayReader(path))):
        pass
      self._loaded_path = path
      self._reader = iter(
        validate_interactions(iter(JsonArrayReader(path)))
      )
      self._recording = []
    else:
      self._recording = validate_recording(source)
      self._loaded_path = None
      self._reader = None
    return self

  def save(self, filename: str | Path) -> None:
    """Write the complete recording as an incrementally emitted JSON array."""
    target = Path(filename)
    if (
      self._loaded_path is not None
      and target.resolve() == self._loaded_path.resolve()
    ):
      return
    if self._loaded_path is not None:
      interactions = validate_interactions(
        iter(JsonArrayReader(self._loaded_path))
      )
    else:
      interactions = iter(self._recording)
    write_json_array(filename, interactions)

  def replay(
    self,
    obj_or_free: Any,
    function_name: str,
    *args: Any,
    **kwargs: Any,
  ) -> Any:
    """Replay exactly one recorded interaction."""
    interaction = self._peek()
    saved_bindings = dict(self._values._bindings)
    try:
      self._preverify(
        interaction, obj_or_free, function_name, args, kwargs
      )

      after = interaction["after"]
      if obj_or_free is not Free:
        self._values.apply(after["obj"], obj_or_free, "after.obj")
      self._apply_arguments(after["args"], args, "after.args")
      self._apply_keywords(after["kwargs"], kwargs, "after.kwargs")

      result = interaction["result"]
      if "return" in result:
        value = self._values.materialize(
          result["return"], "result.return"
        )
        self._consume()
        return value

      error = self._materialize_exception(result["raise"])
      self._consume()
      raise error
    except Exception:
      if self._pending is not None:
        self._values._bindings = saved_bindings
      raise

  def test(
    self,
    lambda_fn: Callable[[], Any],
    obj_or_free: Any,
    function_name: str,
    *args: Any,
    **kwargs: Any,
  ) -> Any:
    """Execute and verify one real interaction against the recording."""
    interaction = self._peek()
    saved_bindings = dict(self._values._bindings)
    try:
      self._preverify(
        interaction, obj_or_free, function_name, args, kwargs
      )

      actual_error = None
      actual_result = None
      try:
        actual_result = lambda_fn()
      except Exception as error:
        actual_error = error

      before = interaction["before"]
      after = interaction["after"]
      if obj_or_free is not Free:
        self._values.match(
          after["obj"], obj_or_free, "after.obj", before["obj"]
        )
      self._match_arguments(
        after["args"], args, "after.args", before["args"]
      )
      self._match_keywords(
        after["kwargs"], kwargs, "after.kwargs", before["kwargs"]
      )

      expected_result = interaction["result"]
      if "return" in expected_result:
        if actual_error is not None:
          raise InterfaceMismatch(
            "result: expected return, actual raised "
            f"{type_name(actual_error)}{actual_error.args!r}"
          )
        self._values.match(
          expected_result["return"], actual_result, "result.return"
        )
        self._consume()
        return actual_result

      if actual_error is None:
        raise InterfaceMismatch(
          f"result: expected raise {expected_result['raise']['$type']}, "
          f"actual returned {actual_result!r}"
        )
      self._match_exception(expected_result["raise"], actual_error)
      self._consume()
      raise actual_error
    except Exception:
      if self._pending is not None:
        self._values._bindings = saved_bindings
      raise

  def record(
    self,
    filter_fn: Callable[[dict[str, Any]], dict[str, Any]],
    lambda_fn: Callable[[], Any],
    obj_or_free: Any,
    function_name: str,
    *args: Any,
    **kwargs: Any,
  ) -> Any:
    """Observe, filter, and append one real interface interaction."""
    if self._loaded_path is not None:
      raise InterfaceGrammarError(
        "cannot append recording interactions to a file-backed playback"
      )
    if not callable(filter_fn) or not callable(lambda_fn):
      raise TypeError("record requires callable filter_fn and lambda_fn")
    if not isinstance(function_name, str) or not function_name:
      raise InterfaceGrammarError("function_name must be a non-empty string")

    call_obj: Any
    before: dict[str, Any]
    if obj_or_free is Free:
      call_obj = {"$free": True}
      before = {}
    else:
      call_obj = self._values.observe(obj_or_free)
      before = {"obj": self._values.observe_again(obj_or_free)}

    before["args"] = [self._values.observe(arg) for arg in args]
    before["kwargs"] = {
      key: self._values.observe(value)
      for key, value in kwargs.items()
    }

    actual_error = None
    actual_result = None
    try:
      actual_result = lambda_fn()
    except Exception as error:
      actual_error = error

    after: dict[str, Any] = {
      "args": [self._values.observe_again(arg) for arg in args],
      "kwargs": {
        key: self._values.observe_again(value)
        for key, value in kwargs.items()
      },
    }
    if obj_or_free is not Free:
      after["obj"] = self._values.observe_again(obj_or_free)

    if actual_error is None:
      result = {"return": self._values.observe_again(actual_result)}
    else:
      result = {
        "raise": {
          "$type": type_name(actual_error),
          "args": [
            self._values.observe_again(item)
            for item in actual_error.args
          ],
        },
      }

    observation = {
      "call": {
        "fn_name": function_name,
        "obj": call_obj,
      },
      "before": before,
      "after": after,
      "result": result,
    }

    filtered = normalize_python(filter_fn(deepcopy(observation)))
    index = len(self._recording)
    validate_interaction(filtered, index)
    bound = set(self._record_bound)
    validate_reference_order(filtered, bound, index)
    self._record_bound = bound
    self._recording.append(filtered)

    if actual_error is not None:
      raise actual_error
    return actual_result

  def _reset_runtime(self) -> None:
    self._recording = []
    self._loaded_path = None
    self._reader = None
    self._cursor = 0
    self._pending = None
    self._record_bound = set()
    self._values.reset()

  def _peek(self) -> dict[str, Any]:
    if self._pending is not None:
      return self._pending

    if self._loaded_path is not None:
      assert self._reader is not None
      try:
        interaction = next(self._reader)
      except StopIteration as error:
        raise InterfaceMismatch(
          f"interaction {self._cursor}: unexpected extra call"
        ) from error
    else:
      if self._cursor >= len(self._recording):
        raise InterfaceMismatch(
          f"interaction {self._cursor}: unexpected extra call"
        )
      interaction = self._recording[self._cursor]

    self._pending = interaction
    return interaction

  def _consume(self) -> None:
    self._cursor += 1
    self._pending = None

  def _preverify(
    self,
    interaction: dict[str, Any],
    obj_or_free: Any,
    function_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
  ) -> None:
    prefix = f"interaction {self._cursor}"
    expected_call = interaction["call"]
    if expected_call["fn_name"] != function_name:
      raise InterfaceMismatch(
        f"{prefix}.call.fn_name: expected "
        f"{expected_call['fn_name']!r}, actual {function_name!r}"
      )

    expected_free = expected_call["obj"] == {"$free": True}
    actual_free = obj_or_free is Free
    if expected_free != actual_free:
      kind = "free function" if expected_free else "member function"
      actual_kind = "free function" if actual_free else "member function"
      raise InterfaceMismatch(
        f"{prefix}.call.obj: expected {kind}, actual {actual_kind}"
      )

    before = interaction["before"]
    if not expected_free:
      self._values.match(
        expected_call["obj"], obj_or_free, f"{prefix}.call.obj"
      )
      self._values.match(
        before["obj"], obj_or_free, f"{prefix}.before.obj"
      )
    self._match_arguments(
      before["args"], args, f"{prefix}.before.args"
    )
    self._match_keywords(
      before["kwargs"], kwargs, f"{prefix}.before.kwargs"
    )

  def _match_arguments(
    self,
    expected: list[Any],
    actual: tuple[Any, ...],
    path: str,
    before: list[Any] | None = None,
  ) -> None:
    if len(expected) != len(actual):
      raise InterfaceMismatch(
        f"{path}.length: expected {len(expected)}, actual {len(actual)}"
      )
    for index, item in enumerate(expected):
      prior = before[index] if before is not None else None
      self._values.match(item, actual[index], f"{path}[{index}]", prior)

  def _match_keywords(
    self,
    expected: dict[str, Any],
    actual: dict[str, Any],
    path: str,
    before: dict[str, Any] | None = None,
  ) -> None:
    if set(expected) != set(actual):
      raise InterfaceMismatch(
        f"{path}.keys: expected {sorted(expected)}, "
        f"actual {sorted(actual)}"
      )
    for key, item in expected.items():
      prior = before.get(key) if before is not None else None
      self._values.match(item, actual[key], f"{path}.{key}", prior)

  def _apply_arguments(
    self,
    expected: list[Any],
    actual: tuple[Any, ...],
    path: str,
  ) -> None:
    if len(expected) != len(actual):
      raise InterfaceMismatch(
        f"{path}.length: expected {len(expected)}, actual {len(actual)}"
      )
    for index, item in enumerate(expected):
      self._values.apply(item, actual[index], f"{path}[{index}]")

  def _apply_keywords(
    self,
    expected: dict[str, Any],
    actual: dict[str, Any],
    path: str,
  ) -> None:
    if set(expected) != set(actual):
      raise InterfaceMismatch(
        f"{path}.keys: expected {sorted(expected)}, "
        f"actual {sorted(actual)}"
      )
    for key, item in expected.items():
      self._values.apply(item, actual[key], f"{path}.{key}")

  def _match_exception(
    self,
    expected: dict[str, Any],
    actual: Exception,
  ) -> None:
    actual_type = type_name(actual)
    if expected["$type"] != actual_type:
      raise InterfaceMismatch(
        f"result.raise.$type: expected {expected['$type']!r}, "
        f"actual {actual_type!r}"
      )
    self._values.match(
      expected["args"], list(actual.args), "result.raise.args"
    )

  def _materialize_exception(
    self,
    expected: dict[str, Any],
  ) -> Exception:
    cls = resolve_type(expected["$type"])
    if not issubclass(cls, Exception):
      raise InterfaceGrammarError(
        f"recorded raised type {expected['$type']!r} is not Exception"
      )
    args = [
      self._values.materialize(item, f"result.raise.args[{index}]")
      for index, item in enumerate(expected["args"])
    ]
    return cls(*args)


__all__ = [
  "Free",
  "InterfaceGrammarError",
  "InterfaceMismatch",
  "InterfacePlayback",
  "Unchanged",
]
