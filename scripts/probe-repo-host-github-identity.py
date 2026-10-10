#!/usr/bin/env python3
"""Discover verified GitHub App installation identity API behaviour.

This probe is read-only.  A rejected identity endpoint is NOT authenticated
actor evidence; record it as unavailable without substituting a runner name.
"""
from __future__ import annotations

import json
import subprocess


def query(route: str, payload: dict | None = None) -> dict:
  command = ["gh", "api", "--method",
             "POST" if payload is not None else "GET", route]
  if payload is not None:
    command += ["--input", "-"]
  outcome = subprocess.run(
    command, input=json.dumps(payload) if payload else None,
    text=True, capture_output=True, timeout=30, check=False,
  )
  if outcome.returncode:
    return {"status": "UNAVAILABLE"}
  try:
    value = json.loads(outcome.stdout)
  except ValueError:
    return {"status": "INVALID_RESPONSE"}
  if not isinstance(value, dict):
    return {"status": "INVALID_RESPONSE"}
  if route == "user":
    login = value.get("login")
  elif route == "graphql":
    viewer = value.get("data", {}).get("viewer")
    login = viewer.get("login") if isinstance(viewer, dict) else None
  else:
    login = None
  return {
    "status": "VERIFIED_LOGIN" if isinstance(login, str) and login
    else "NO_LOGIN",
    "login": login if isinstance(login, str) else None,
    "installation_repositories": (
      len(value.get("repositories", []))
      if route == "installation/repositories"
      else None
    ),
  }


def main() -> int:
  results = {
    "user": query("user"),
    "graphql_viewer": query(
      "graphql", {"query": "query { viewer { login } }"}
    ),
    "installation_repositories": query("installation/repositories"),
  }
  print(json.dumps(results, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
