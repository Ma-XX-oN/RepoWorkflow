"""Explicit GitHub Actions artifact staging and retrieval commands.

Workflow jobs transfer these bundles with actions/upload-artifact@v4 and
actions/download-artifact@v4. This interface never certifies PASS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .github_result_transport import TransportError, fetch_bundle, publish_bundle


def _load(path: Path) -> dict:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise TransportError("missing or invalid request") from exc
  if not isinstance(data, dict):
    raise TransportError("request must be an object")
  return data


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("operation", choices=("publish", "fetch"))
  parser.add_argument("--request", type=Path, required=True)
  parser.add_argument("--source", type=Path, required=True)
  parser.add_argument("--destination", type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    request = _load(args.request)
    requirements = request.get("requirements")
    if not isinstance(requirements, dict):
      raise TransportError("missing requirements")
    declared = requirements.get("artifacts")
    if not isinstance(declared, list):
      raise TransportError("invalid artifact declaration")
    if request.get("operation") != args.operation:
      raise TransportError("request operation mismatch")
    if args.operation == "publish":
      records = {}
      for name in declared:
        if not isinstance(name, str) or not name or name in records:
          raise TransportError("invalid or duplicate artifact declaration")
        if name in (".", "..", "manifest.json") or "/" in name or "\\" in name:
          raise TransportError("unsafe artifact name")
        path = args.source / name
        if path.is_symlink() or not path.is_file():
          raise TransportError("missing or unsafe declared artifact")
        records[name] = path.read_bytes()
      publish_bundle(request, records, args.destination)
    else:
      if args.destination.exists():
        raise TransportError("retrieval destination already exists")
      records = fetch_bundle(args.source, request.get("invocation_id"),
                             request.get("candidate"), declared)
      args.destination.mkdir(parents=True, exist_ok=False)
      for name, data in records.items():
        (args.destination / name).write_bytes(data)
  except (TransportError, OSError) as exc:
    print(f"repo-ci GitHub transport incomplete: {exc}", file=sys.stderr)
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
