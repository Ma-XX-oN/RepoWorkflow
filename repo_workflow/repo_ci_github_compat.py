"""Legacy github-* CLI compatibility boundary for repo-ci-github migration.

The public CLI imports only this provider compatibility surface. The existing
GitHub adapter implementation remains authoritative for legacy output formats
until the #67 equivalence acceptance tests permit a semantic cutover.
"""
from __future__ import annotations

from pathlib import Path

from .github_adapter import (
  AdapterError, github_matrix as _github_matrix,
  github_mode as _github_mode,
  github_prepare_context as _github_prepare_context,
  github_prepare_runner as _github_prepare_runner,
  load_github_config as _load_github_config,
  request_changed as _request_changed,
)


def request_changed(root: Path, event_name: str, event_path: Path) -> bool:
  return _request_changed(root, event_name, event_path)


def github_mode(root: Path, event_name: str, event_path: Path,
                branch: str, integration_branch: str) -> str:
  return _github_mode(root, event_name, event_path, branch, integration_branch)


def load_github_config(root: Path) -> dict:
  return _load_github_config(root)


def github_matrix(config: dict, github_config: dict) -> dict:
  return _github_matrix(config, github_config)


def github_prepare_runner(github_config: dict) -> str:
  return _github_prepare_runner(github_config)


def github_prepare_context(config: dict, github_config: dict) -> dict:
  return _github_prepare_context(config, github_config)
