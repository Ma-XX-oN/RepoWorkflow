from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys
import tempfile
import time
import uuid

from .git import GitError, git, head_sha


@dataclass
class LaneDiagnostics:
  root: Path
  command: tuple[str, ...]
  started: float = field(default_factory=time.perf_counter)
  started_utc: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )
  provider_counts: dict[str, int] = field(default_factory=dict)
  provider_seconds: dict[str, float] = field(default_factory=dict)
  cache_hits: dict[str, int] = field(default_factory=dict)
  cache_misses: dict[str, int] = field(default_factory=dict)
  phase_seconds: dict[str, float] = field(default_factory=dict)
  semantic_edges: list[tuple[int, int]] = field(default_factory=list)
  routed_edges: list[dict] = field(default_factory=list)
  error: str | None = None

  def provider(
    self,
    family: str,
    issue: int,
    call,
    *,
    index: int | None = None,
    total: int | None = None,
  ):
    if total is not None and index is not None:
      print(
        f"Refreshing {family}: {index}/{total} (#{issue})",
        file=sys.stderr,
      )
    else:
      print(f"Refreshing {family}: #{issue}", file=sys.stderr)
    started = time.perf_counter()
    try:
      return call()
    finally:
      elapsed = time.perf_counter() - started
      self.provider_counts[family] = self.provider_counts.get(family, 0) + 1
      self.provider_seconds[family] = (
        self.provider_seconds.get(family, 0.0) + elapsed
      )

  def hit(self, family: str, count: int = 1) -> None:
    self.cache_hits[family] = self.cache_hits.get(family, 0) + count

  def miss(self, family: str, count: int = 1) -> None:
    self.cache_misses[family] = self.cache_misses.get(family, 0) + count

  def phase(self, name: str, started: float) -> None:
    self.phase_seconds[name] = self.phase_seconds.get(name, 0.0) + (
      time.perf_counter() - started
    )

  def set_semantic_edges(self, edges: list[tuple[int, int]]) -> None:
    self.semantic_edges = sorted(set(edges))

  def finish(self, *, error: Exception | None = None) -> Path | None:
    if error is not None:
      self.error = str(error)
    try:
      return self._write()
    except Exception as diagnostic_error:
      print(
        "RepoWorkflow warning: could not write lane invocation diagnostics: "
        f"{diagnostic_error}",
        file=sys.stderr,
      )
      return None

  def _write(self) -> Path:
    total = time.perf_counter() - self.started
    common = Path(
      git(self.root, "rev-parse", "--git-common-dir").stdout.strip()
    )
    if not common.is_absolute():
      common = (self.root / common).resolve()
    directory = common / "repoworkflow" / "diagnostics" / "lanes"
    directory.mkdir(parents=True, exist_ok=True)
    identifier = str(uuid.uuid4())
    path = directory / f"lane-invocation--{identifier}.json"
    try:
      commit = head_sha(self.root)
    except GitError:
      commit = None
    value = {
      "schema_version": 1,
      "invocation_id": identifier,
      "started_utc": self.started_utc,
      "repository_head": commit,
      "command": list(self.command),
      "elapsed_seconds": total,
      "provider_calls": dict(sorted(self.provider_counts.items())),
      "provider_seconds": dict(sorted(self.provider_seconds.items())),
      "cache_hits": dict(sorted(self.cache_hits.items())),
      "cache_misses": dict(sorted(self.cache_misses.items())),
      "phase_seconds": dict(sorted(self.phase_seconds.items())),
      "semantic_edges": [list(edge) for edge in self.semantic_edges],
      "routed_edges": self.routed_edges,
      "success": self.error is None,
      "error": self.error,
    }
    descriptor, temporary = tempfile.mkstemp(
      prefix=f".{path.name}.",
      suffix=".tmp",
      dir=directory,
    )
    temporary_path = Path(temporary)
    try:
      with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
      os.replace(temporary_path, path)
    finally:
      try:
        temporary_path.unlink()
      except FileNotFoundError:
        pass
    return path

  def debug_lines(self) -> tuple[str, ...]:
    provider_total = sum(self.provider_counts.values())
    lines = [
      "DATA SOURCES",
      f"  provider requests: {provider_total}",
    ]
    for family in sorted(set(self.cache_hits) | set(self.cache_misses)):
      lines.append(
        f"  {family}: cache hits={self.cache_hits.get(family, 0)} "
        f"misses={self.cache_misses.get(family, 0)}"
      )
    lines.append("")
    lines.append("TIMING")
    for family, seconds in sorted(self.provider_seconds.items()):
      lines.append(f"  provider {family}: {seconds:.3f}s")
    for phase, seconds in sorted(self.phase_seconds.items()):
      lines.append(f"  {phase}: {seconds:.3f}s")
    if self.semantic_edges:
      lines.append("")
      lines.append("DIRECT EDGES")
      lines.extend(
        f"  {source} -> {target}"
        for source, target in self.semantic_edges
      )
    if self.routed_edges:
      lines.append("")
      lines.append("ROUTES")
      lines.extend(
        "  "
        + f"{edge['source']} -> {edge['target']} "
        + f"{edge.get('kind', 'route')}"
        for edge in self.routed_edges
      )
    return tuple(lines)
