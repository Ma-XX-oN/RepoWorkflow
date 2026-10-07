from __future__ import annotations

from dataclasses import dataclass
import re


QUANTIFIER = "_quantifier"
SWITCHES = "_switches"
TERMINAL = ""


class CommandGrammarError(ValueError):
  pass


@dataclass(frozen=True)
class Quantifier:
  minimum: int
  maximum: int | None


def validate_description(value: object, label: str) -> None:
  if not isinstance(value, str) or not value:
    raise CommandGrammarError(f"{label} must be a non-empty description string")


def parse_quantifier(value: object, *, label: str) -> Quantifier:
  if value is None:
    return Quantifier(1, 1)
  if not isinstance(value, str):
    raise CommandGrammarError(f"{label} must be a regex-style quantifier")
  if value == "?":
    return Quantifier(0, 1)
  if value == "*":
    return Quantifier(0, None)
  if value == "+":
    return Quantifier(1, None)
  match = re.fullmatch(r"\{(\d+)(?:,(\d*)?)?\}", value)
  if match is None:
    raise CommandGrammarError(f"{label} has invalid quantifier {value!r}")
  minimum = int(match.group(1))
  comma = "," in value
  upper = match.group(2)
  maximum = minimum if not comma else (None if upper == "" else int(upper))
  if maximum is not None and maximum < minimum:
    raise CommandGrammarError(f"{label} maximum is less than minimum")
  return Quantifier(minimum, maximum)


def validate_param_slot(slot: object, label: str) -> None:
  if not isinstance(slot, dict):
    raise CommandGrammarError(f"{label} must be a parameter-alternative dictionary")
  parse_quantifier(slot.get(QUANTIFIER), label=f"{label}[{QUANTIFIER!r}]")
  alternatives = [name for name in slot if name != QUANTIFIER]
  if not alternatives:
    raise CommandGrammarError(f"{label} must define at least one parameter alternative")
  for token in alternatives:
    if not isinstance(token, str) or not token:
      raise CommandGrammarError(f"{label} parameter names must be non-empty strings")
    entry = slot[token]
    if not callable(entry):
      validate_description(entry, f"{label}[{token!r}]")


def validate_switch_entry(entry: object, label: str) -> None:
  if isinstance(entry, str):
    validate_description(entry, label)
    return
  if isinstance(entry, list):
    for index, slot in enumerate(entry):
      validate_param_slot(slot, f"{label}[{index}]")
    return
  if not isinstance(entry, dict):
    raise CommandGrammarError(f"{label} must be help, parameters, or a switch node")
  allowed = {TERMINAL, QUANTIFIER}
  unknown = set(entry) - allowed
  if unknown:
    names = ", ".join(repr(name) for name in sorted(unknown))
    raise CommandGrammarError(f"{label} contains unsupported switch field(s): {names}")
  if TERMINAL in entry:
    validate_description(entry[TERMINAL], f"{label}[{TERMINAL!r}]")
  parse_quantifier(entry.get(QUANTIFIER), label=f"{label}[{QUANTIFIER!r}]")


def validate_switches(value: object, label: str) -> None:
  if callable(value):
    return
  if not isinstance(value, dict):
    raise CommandGrammarError(f"{label} must be a switch dictionary or provider")
  for token, entry in value.items():
    if not isinstance(token, str) or not token.startswith("--"):
      raise CommandGrammarError(f"{label} keys must be --switch tokens")
    validate_switch_entry(entry, f"{label}[{token!r}]")


def switch_quantifier(entry: object) -> Quantifier:
  if isinstance(entry, dict):
    return parse_quantifier(entry.get(QUANTIFIER), label=f"switch {QUANTIFIER}")
  return Quantifier(0, 1)


def switch_description(entry: object) -> str | None:
  if isinstance(entry, str):
    return entry
  if isinstance(entry, dict):
    value = entry.get(TERMINAL)
    return value if isinstance(value, str) else None
  return None


def slot_candidates(slot: dict, context) -> dict[str, str | None]:
  result: dict[str, str | None] = {}
  for token, entry in slot.items():
    if token == QUANTIFIER:
      continue
    if callable(entry):
      values = entry(context)
      if not isinstance(values, dict):
        raise CommandGrammarError(
          "parameter completion provider must return a dictionary"
        )
      for name, description in values.items():
        if not isinstance(name, str) or not name:
          raise CommandGrammarError("parameter completion names must be strings")
        if description is not None and not isinstance(description, str):
          raise CommandGrammarError(
            "parameter completion descriptions must be strings"
          )
        result[name] = description
    else:
      result[token] = entry
  return result


def consume_switch(
  entry: object,
  words: tuple[str, ...],
  index: int,
  context,
) -> tuple[int, dict | None, int]:
  if not isinstance(entry, list):
    return index, None, 0
  for slot in entry:
    quantifier = parse_quantifier(
      slot.get(QUANTIFIER),
      label="parameter quantifier",
    )
    count = 0
    while index < len(words):
      candidates = slot_candidates(slot, context.at(words, index))
      if words[index] not in candidates:
        break
      if quantifier.maximum is not None and count >= quantifier.maximum:
        break
      count += 1
      index += 1
    if count < quantifier.minimum:
      if index == len(words):
        return index, slot, count
      raise CommandGrammarError(f"invalid switch parameter: {words[index]}")
  return index, None, 0
