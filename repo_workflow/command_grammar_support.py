from __future__ import annotations

from dataclasses import dataclass
import re


QUANTIFIER = "_quantifier"
SWITCHES = "_switches"
PARAMS = "_params"
ORDERED = "_ordered"
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


def is_parameter(token: str) -> bool:
  return len(token) > 2 and token.startswith("<") and token.endswith(">")


def validate_param_entry(entry: object, label: str) -> None:
  if callable(entry):
    return
  validate_description(entry, label)


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
    validate_param_entry(slot[token], f"{label}[{token!r}]")


def validate_params(value: object, label: str) -> None:
  if not isinstance(value, list) or not value:
    raise CommandGrammarError(f"{label} must be a non-empty parameter-position list")
  for index, slot in enumerate(value):
    validate_param_slot(slot, f"{label}[{index}]")


def validate_ordered(value: object, label: str) -> None:
  if not isinstance(value, list) or not value:
    raise CommandGrammarError(f"{label} must be a non-empty ordered-position list")
  for index, slot in enumerate(value):
    if not isinstance(slot, dict):
      raise CommandGrammarError(f"{label}[{index}] must be an alternatives dictionary")
    if QUANTIFIER in slot:
      raise CommandGrammarError(
        f"{label}[{index}] cannot quantify an ordered position; "
        f"quantify the complete {ORDERED} sequence instead"
      )
    if not slot:
      raise CommandGrammarError(f"{label}[{index}] must define an alternative")
    for token, entry in slot.items():
      if not isinstance(token, str) or not token:
        raise CommandGrammarError(f"{label}[{index}] keys must be strings")
      validate_param_entry(entry, f"{label}[{index}][{token!r}]")


def validate_switch_entry(entry: object, label: str) -> None:
  if isinstance(entry, str):
    validate_description(entry, label)
    return
  if not isinstance(entry, dict):
    raise CommandGrammarError(
      f"{label} must be help or a switch node with {PARAMS!r}"
    )
  allowed = {TERMINAL, QUANTIFIER, PARAMS}
  unknown = set(entry) - allowed
  if unknown:
    names = ", ".join(repr(name) for name in sorted(unknown))
    raise CommandGrammarError(f"{label} contains unsupported switch field(s): {names}")
  if TERMINAL in entry:
    validate_description(entry[TERMINAL], f"{label}[{TERMINAL!r}]")
  if PARAMS in entry:
    validate_params(entry[PARAMS], f"{label}[{PARAMS!r}]")
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
  if not isinstance(entry, dict) or QUANTIFIER not in entry:
    return Quantifier(0, 1)
  return parse_quantifier(entry[QUANTIFIER], label=f"switch {QUANTIFIER}")


def switch_description(entry: object) -> str | None:
  if isinstance(entry, str):
    return entry
  if isinstance(entry, dict):
    value = entry.get(TERMINAL)
    return value if isinstance(value, str) else None
  return None


def switch_params(entry: object) -> list[dict]:
  if isinstance(entry, dict):
    value = entry.get(PARAMS, [])
    return value if isinstance(value, list) else []
  return []


def _provider_values(provider, context) -> dict[str, str | None]:
  values = provider(context)
  if not isinstance(values, dict):
    raise CommandGrammarError("parameter completion provider must return a dictionary")
  result: dict[str, str | None] = {}
  for name, description in values.items():
    if not isinstance(name, str) or not name:
      raise CommandGrammarError("parameter completion names must be strings")
    if description is not None and not isinstance(description, str):
      raise CommandGrammarError("parameter completion descriptions must be strings")
    result[name] = description
  return result


def slot_candidates(
  slot: dict,
  context,
  *,
  describe_generic: bool = False,
) -> dict[str, str | None]:
  result: dict[str, str | None] = {}
  for token, entry in slot.items():
    if token == QUANTIFIER:
      continue
    if callable(entry):
      result.update(_provider_values(entry, context))
    elif is_parameter(token):
      if describe_generic:
        result[token] = entry
    else:
      result[token] = entry
  return result


def slot_matches(slot: dict, token: str, context) -> bool:
  for name, entry in slot.items():
    if name == QUANTIFIER:
      continue
    if callable(entry):
      if token in _provider_values(entry, context):
        return True
    elif is_parameter(name):
      if token and not token.startswith("--"):
        return True
    elif token == name:
      return True
  return False


def consume_switch(
  entry: object,
  words: tuple[str, ...],
  index: int,
  context,
) -> tuple[int, dict | None, int]:
  params = switch_params(entry)
  if not params:
    return index, None, 0
  for slot in params:
    quantifier = parse_quantifier(
      slot.get(QUANTIFIER),
      label="parameter quantifier",
    )
    count = 0
    while index < len(words):
      current = context.at(words, index)
      if not slot_matches(slot, words[index], current):
        break
      if quantifier.maximum is not None and count >= quantifier.maximum:
        break
      count += 1
      index += 1
    can_repeat = quantifier.maximum is None or count < quantifier.maximum
    if index == len(words) and can_repeat:
      return index, slot, count
    if count < quantifier.minimum:
      raise CommandGrammarError(f"invalid switch parameter: {words[index]}")
  return index, None, 0


def ordered_match(slot: dict, token: str, context) -> bool:
  return slot_matches(slot, token, context)
