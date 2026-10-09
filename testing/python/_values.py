"""Logical object identity, comparison, observation, and replay mutation."""

from __future__ import annotations

import importlib
from typing import Any

from ._grammar import InterfaceGrammarError


class InterfaceMismatch(AssertionError):
  """Raised at the first consequential difference from a recording."""


def type_name(value: Any) -> str:
  cls = value if isinstance(value, type) else type(value)
  return f"{cls.__module__}.{cls.__qualname__}"


def resolve_type(name: str) -> type:
  module_name, _, qualname = name.rpartition(".")
  if not module_name or not qualname:
    raise InterfaceGrammarError(f"invalid type identifier {name!r}")
  try:
    value: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
      value = getattr(value, part)
  except (ImportError, AttributeError) as error:
    raise InterfaceGrammarError(
      f"cannot resolve recorded type {name!r}"
    ) from error
  if not isinstance(value, type):
    raise InterfaceGrammarError(f"recorded type {name!r} is not a class")
  return value


class ValueEngine:
  """Own logical bindings for one recording/playback session."""

  def __init__(self):
    self._bindings: dict[str, Any] = {}
    self._record_ids: dict[int, str] = {}
    self._next_ids: dict[str, int] = {}

  def reset(self) -> None:
    self._bindings.clear()
    self._record_ids.clear()
    self._next_ids.clear()

  def _new_name(self, value: Any) -> str:
    base = type(value).__name__.lower() or "object"
    number = self._next_ids.get(base, 0) + 1
    self._next_ids[base] = number
    return f"{base}_{number}"

  def _record_identity(self, value: Any) -> tuple[str, bool]:
    process_id = id(value)
    if process_id in self._record_ids:
      return self._record_ids[process_id], False
    name = self._new_name(value)
    self._record_ids[process_id] = name
    return name, True

  def observe(self, value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int, float)):
      return value

    if isinstance(value, list):
      name, fresh = self._record_identity(value)
      if not fresh:
        return {"$ref": name}
      return {
        "$new": name,
        "$type": "builtins.list",
        "items": [self.observe(item) for item in value],
      }

    if isinstance(value, dict):
      if any(not isinstance(key, str) for key in value):
        raise InterfaceGrammarError(
          "recorded dictionaries require string keys"
        )
      name, fresh = self._record_identity(value)
      if not fresh:
        return {"$ref": name}
      return {
        "$new": name,
        "$type": "builtins.dict",
        "keys": list(value.keys()),
        "items": {
          key: self.observe(item)
          for key, item in value.items()
        },
      }

    if isinstance(value, tuple):
      raise InterfaceGrammarError(
        "tuple values require an explicit stream grammar before recording"
      )

    name, fresh = self._record_identity(value)
    if not fresh:
      return {"$ref": name}
    result = {"$new": name, "$type": type_name(value)}
    if hasattr(value, "__dict__"):
      result.update({
        key: self.observe(item)
        for key, item in vars(value).items()
      })
    return result

  def observe_again(self, value: Any) -> Any:
    """Observe post-state, preserving identities already introduced."""
    if value is None or isinstance(value, (bool, str, int, float)):
      return value

    if isinstance(value, list):
      name, fresh = self._record_identity(value)
      result = {
        "$new" if fresh else "$ref": name,
        "$type": "builtins.list",
        "items": [self.observe_again(item) for item in value],
      }
      if not fresh:
        result.pop("$type")
      return result

    if isinstance(value, dict):
      if any(not isinstance(key, str) for key in value):
        raise InterfaceGrammarError(
          "recorded dictionaries require string keys"
        )
      name, fresh = self._record_identity(value)
      result = {
        "$new" if fresh else "$ref": name,
        "$type": "builtins.dict",
        "keys": list(value.keys()),
        "items": {
          key: self.observe_again(item)
          for key, item in value.items()
        },
      }
      if not fresh:
        result.pop("$type")
      return result

    if isinstance(value, tuple):
      raise InterfaceGrammarError(
        "tuple values require an explicit stream grammar before recording"
      )

    name, fresh = self._record_identity(value)
    result = {
      "$new" if fresh else "$ref": name,
      "$type": type_name(value),
    }
    if not fresh:
      result.pop("$type")
    if hasattr(value, "__dict__"):
      result.update({
        key: self.observe_again(item)
        for key, item in vars(value).items()
      })
    return result

  def _mismatch(self, path: str, expected: Any, actual: Any) -> None:
    raise InterfaceMismatch(
      f"{path}: expected {expected!r}, actual {actual!r}"
    )

  def _check_type(
    self,
    expected: dict[str, Any],
    actual: Any,
    path: str,
  ) -> None:
    expected_type = expected.get("$type")
    if expected_type is not None and type_name(actual) != expected_type:
      self._mismatch(path + ".$type", expected_type, type_name(actual))

  def _bind_or_check(
    self,
    expected: dict[str, Any],
    actual: Any,
    path: str,
  ) -> None:
    if "$new" in expected:
      name = expected["$new"]
      if name in self._bindings:
        raise InterfaceMismatch(
          f"{path}: logical object {name!r} introduced more than once"
        )
      self._bindings[name] = actual
    elif "$ref" in expected:
      name = expected["$ref"]
      if name not in self._bindings:
        raise InterfaceMismatch(
          f"{path}: unknown logical object reference {name!r}"
        )
      if self._bindings[name] is not actual:
        raise InterfaceMismatch(
          f"{path}: expected logical object {name!r}"
        )

  def match(
    self,
    expected: Any,
    actual: Any,
    path: str,
    before: Any | None = None,
  ) -> None:
    if isinstance(expected, dict) and "$unchanged" in expected:
      if before is None:
        raise InterfaceGrammarError(
          f"{path}: Unchanged has no corresponding before value"
        )
      selector = expected["$unchanged"]
      if selector is True:
        self.match(before, actual, path)
        return
      keys = selector["keys"]
      if not isinstance(before, dict):
        raise InterfaceGrammarError(
          f"{path}: selective Unchanged requires object/mapping before state"
        )
      for key in keys:
        if key not in before:
          raise InterfaceGrammarError(
            f"{path}: Unchanged key {key!r} missing from before state"
          )
        current = self._read_field(actual, key, path)
        self.match(before[key], current, f"{path}.{key}")
      return

    if isinstance(expected, dict) and (
      "$new" in expected or "$ref" in expected or "$type" in expected
    ):
      self._bind_or_check(expected, actual, path)
      self._check_type(expected, actual, path)

      type_id = expected.get("$type")
      if type_id == "builtins.list" or (
        "$ref" in expected and isinstance(actual, list)
      ):
        if "items" in expected:
          prior = before.get("items") if isinstance(before, dict) else None
          self.match(
            expected["items"], list(actual), path + ".items", prior
          )
        return
      if type_id == "builtins.dict" or (
        "$ref" in expected and isinstance(actual, dict)
      ):
        if "keys" in expected and list(actual.keys()) != expected["keys"]:
          self._mismatch(
            path + ".keys", expected["keys"], list(actual.keys())
          )
        if "items" in expected:
          prior_items = (
            before.get("items") if isinstance(before, dict) else None
          )
          for key, item in expected["items"].items():
            if key not in actual:
              raise InterfaceMismatch(
                f"{path}.items.{key}: missing dictionary key"
              )
            prior = (
              prior_items.get(key)
              if isinstance(prior_items, dict)
              else None
            )
            self.match(
              item, actual[key], f"{path}.items.{key}", prior
            )
        return

      for key, item in expected.items():
        if key.startswith("$"):
          continue
        current = self._read_field(actual, key, path)
        prior = before.get(key) if isinstance(before, dict) else None
        self.match(item, current, f"{path}.{key}", prior)
      return

    if isinstance(expected, list):
      if not isinstance(actual, list):
        self._mismatch(path, expected, actual)
      if len(expected) != len(actual):
        self._mismatch(path + ".length", len(expected), len(actual))
      for index, item in enumerate(expected):
        prior = (
          before[index]
          if isinstance(before, list) and index < len(before)
          else None
        )
        self.match(item, actual[index], f"{path}[{index}]", prior)
      return

    if isinstance(expected, dict):
      if not isinstance(actual, dict):
        self._mismatch(path, expected, actual)
      if set(expected) != set(actual):
        self._mismatch(path + ".keys", sorted(expected), sorted(actual))
      for key, item in expected.items():
        prior = before.get(key) if isinstance(before, dict) else None
        self.match(item, actual[key], f"{path}.{key}", prior)
      return

    if type(expected) is not type(actual) or expected != actual:
      self._mismatch(path, expected, actual)

  def _read_field(self, actual: Any, key: str, path: str) -> Any:
    if isinstance(actual, dict):
      if key not in actual:
        raise InterfaceMismatch(f"{path}.{key}: missing field")
      return actual[key]
    if not hasattr(actual, key):
      raise InterfaceMismatch(f"{path}.{key}: missing attribute")
    return getattr(actual, key)

  def _applied_value(
    self,
    expected: Any,
    current: Any,
    path: str,
  ) -> Any:
    if isinstance(expected, dict) and "$unchanged" in expected:
      return current
    if isinstance(expected, dict) and "$ref" in expected:
      self.apply(expected, current, path)
      return current
    return self.materialize(expected, path)

  def apply(self, expected: Any, actual: Any, path: str) -> None:
    if isinstance(expected, dict) and "$unchanged" in expected:
      return

    if isinstance(expected, dict) and (
      "$new" in expected or "$ref" in expected or "$type" in expected
    ):
      self._bind_or_check(expected, actual, path)
      self._check_type(expected, actual, path)
      type_id = expected.get("$type")

      if type_id == "builtins.list" or isinstance(actual, list):
        if "items" in expected:
          new_items = []
          for index, item in enumerate(expected["items"]):
            current = actual[index] if index < len(actual) else None
            new_items.append(
              self._applied_value(item, current, f"{path}.items[{index}]")
            )
          actual[:] = new_items
        return

      if type_id == "builtins.dict" or isinstance(actual, dict):
        if "items" in expected:
          updates = {}
          for key, item in expected["items"].items():
            current = actual.get(key)
            updates[key] = self._applied_value(
              item, current, f"{path}.items.{key}"
            )
          if "keys" in expected:
            ordered = {}
            for key in expected["keys"]:
              if key in updates:
                ordered[key] = updates[key]
              elif key in actual:
                ordered[key] = actual[key]
              else:
                raise InterfaceMismatch(
                  f"{path}.items.{key}: missing value for recorded key"
                )
            actual.clear()
            actual.update(ordered)
          else:
            actual.update(updates)
        return

      for key, item in expected.items():
        if key.startswith("$"):
          continue
        current = getattr(actual, key, None)
        if isinstance(item, dict) and "$ref" in item and current is not None:
          self.apply(item, current, f"{path}.{key}")
        elif isinstance(item, dict) and "$unchanged" in item:
          continue
        else:
          setattr(actual, key, self.materialize(item, f"{path}.{key}"))
      return

    if isinstance(actual, list) and isinstance(expected, list):
      new_items = []
      for index, item in enumerate(expected):
        current = actual[index] if index < len(actual) else None
        new_items.append(
          self._applied_value(item, current, f"{path}[{index}]")
        )
      actual[:] = new_items
      return

    if isinstance(actual, dict) and isinstance(expected, dict):
      new_items = {}
      for key, item in expected.items():
        new_items[key] = self._applied_value(
          item, actual.get(key), f"{path}.{key}"
        )
      actual.clear()
      actual.update(new_items)
      return

    if expected != actual:
      raise InterfaceMismatch(
        f"{path}: replay cannot mutate immutable value "
        f"from {actual!r} to {expected!r}"
      )

  def materialize(self, spec: Any, path: str = "result") -> Any:
    if isinstance(spec, list):
      return [
        self.materialize(item, f"{path}[{index}]")
        for index, item in enumerate(spec)
      ]
    if not isinstance(spec, dict):
      return spec

    if "$unchanged" in spec:
      raise InterfaceGrammarError(
        f"{path}: Unchanged cannot materialize a standalone value"
      )
    if "$ref" in spec:
      name = spec["$ref"]
      if name not in self._bindings:
        raise InterfaceMismatch(
          f"{path}: unknown logical object reference {name!r}"
        )
      return self._bindings[name]
    if "$new" in spec:
      name = spec["$new"]
      if name in self._bindings:
        raise InterfaceMismatch(
          f"{path}: logical object {name!r} introduced more than once"
        )
      type_id = spec.get("$type")
      if type_id == "builtins.list":
        value: Any = []
        self._bindings[name] = value
        value.extend(
          self.materialize(item, f"{path}.items[{index}]")
          for index, item in enumerate(spec.get("items", []))
        )
        return value
      if type_id == "builtins.dict":
        value = {}
        self._bindings[name] = value
        items = spec.get("items", {})
        keys = spec.get("keys", list(items))
        for key in keys:
          if key not in items:
            raise InterfaceGrammarError(
              f"{path}.items.{key}: missing value for recorded key"
            )
          value[key] = self.materialize(
            items[key], f"{path}.items.{key}"
          )
        return value
      if type_id is None:
        raise InterfaceGrammarError(
          f"{path}: $new requires $type when materializing a result"
        )
      cls = resolve_type(type_id)
      value = cls.__new__(cls)
      self._bindings[name] = value
      for key, item in spec.items():
        if key.startswith("$"):
          continue
        setattr(value, key, self.materialize(item, f"{path}.{key}"))
      return value

    return {
      key: self.materialize(item, f"{path}.{key}")
      for key, item in spec.items()
    }
