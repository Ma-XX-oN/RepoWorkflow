"""Pure RED outcome classification against predeclared behavioural expectations.

The storage format for declarations is deliberately outside this module.
Callers must establish the expected outcome before launching the test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedExpectation:
  """A pre-execution expected exit and independently declared output signature."""
  exit_code: int
  output_contains: str


@dataclass(frozen=True)
class RedObservation:
  exit_code: int | None
  stdout: str
  stderr: str
  executed: bool


@dataclass(frozen=True)
class RedDecision:
  status: str
  reason: str


def classify_red(
  expectation: RedExpectation | None,
  observation: RedObservation,
) -> RedDecision:
  """Distinguish intended failure, unexpected pass/failure, and unavailable run."""
  if expectation is None:
    return RedDecision("INCOMPLETE", "expected-failure-declaration-missing")
  if (
    type(expectation.exit_code) is not int
    or expectation.exit_code <= 0
    or not isinstance(expectation.output_contains, str)
    or not expectation.output_contains
  ):
    return RedDecision("INCOMPLETE", "invalid-expected-failure-declaration")
  if not observation.executed or observation.exit_code is None:
    return RedDecision("INCOMPLETE", "selected-test-not-executed")
  if observation.exit_code == 0:
    return RedDecision("NOT_RED", "selected-test-unexpectedly-passed")
  if observation.exit_code < 0:
    return RedDecision("INCOMPLETE", "test-process-terminated")
  if (
    observation.exit_code == expectation.exit_code
    and expectation.output_contains in (
      observation.stdout + "\n" + observation.stderr
    )
  ):
    return RedDecision("RED", "declared-behavioural-failure-observed")
  return RedDecision("FAIL", "unexpected-test-failure")
