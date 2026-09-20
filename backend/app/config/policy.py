"""Loader for priority_config.yaml - the city's scoring and SLA policy.

Kept deliberately thin: this module reads YAML and hands out plain dicts. All
the meaning lives in the YAML file, which is the artefact an officer, an auditor
or a councillor is meant to read. Nothing in the codebase may hard-code a weight
that is not in that file.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "priority_config.yaml"


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    """Read and cache the policy file."""
    try:
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - fatal misconfiguration
        raise RuntimeError(f"Could not read priority policy at {CONFIG_PATH}: {exc}") from exc

    for section in ("priority", "bands", "sla", "dedup", "confidence"):
        if section not in data:
            raise RuntimeError(f"priority_config.yaml is missing the '{section}' section")
    return data


def reload_policy() -> dict[str, Any]:
    """Drop the cache and re-read (used by tests and by the config viewer)."""
    load_policy.cache_clear()
    return load_policy()


def priority_config() -> dict[str, Any]:
    return load_policy()["priority"]


def bands_config() -> dict[str, int]:
    return load_policy()["bands"]


def sla_config() -> dict[str, Any]:
    return load_policy()["sla"]


def dedup_config() -> dict[str, Any]:
    return load_policy()["dedup"]


def confidence_config() -> dict[str, Any]:
    return load_policy()["confidence"]


def policy_source() -> str:
    """Raw YAML text, shown verbatim in the dashboard's policy viewer."""
    try:
        return CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return ""
