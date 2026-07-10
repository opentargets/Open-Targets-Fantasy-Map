from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "ontology": {"skip_roots": True, "root_ids": []},
    "map": {
        "name": "Open Targets Atlas",
        "width": 2600,
        "height": 1600,
        "cells": None,
        "cell_multiplier": 4.0,
        "max_cells": 100000,
        "max_routes": 0,
        "version": "1.134.2",
        "distance_scale": 5,
        "population_rate": 1000,
        "urbanization": 1,
        "style": "ancient",
    },
    "layers": {
        "elevation": None,
        "precipitation": None,
        "temperature": None,
        "phase_drug_count": None,
        "biome": None,
        "population": None,
        "religion": None,
        "good": None,
    },
    "notes": {"include_burg_notes": True},
    "svg": {
        "max_burg_icons": 5000,
        "shape_rendering": "optimizeSpeed",
        "state_fill": False,
        "state_halo": False,
        "province_labels": False,
        "cells_layer": False,
        "clip_to_land": False,
    },
}


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = _load_yaml_like(text)

    return config_with_defaults(loaded, config_path.parent)


def config_with_defaults(loaded: dict[str, Any], config_dir: str | Path | None = None) -> dict[str, Any]:
    config = _deep_merge(DEFAULT_CONFIG, loaded)
    if config_dir is not None:
        config["_config_dir"] = str(Path(config_dir).resolve())
    return config


def _load_yaml_like(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data or {}
    except ModuleNotFoundError:
        return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by the example config.

    This is intentionally conservative. It supports nested mappings,
    inline lists, quoted scalars, booleans, nulls, and numbers. Install
    PyYAML if you need anchors, block lists, multiline strings, or tags.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- "):
            raise ValueError("The fallback YAML parser does not support block lists; use inline lists or install PyYAML")

        indent = len(line) - len(line.lstrip(" "))
        key, sep, value = line.strip().partition(":")
        if not sep:
            raise ValueError(f"Invalid config line: {raw_line!r}")

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        value = value.strip()
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _parse_scalar(value: str) -> Any:
    if value in {"null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except Exception:
            inner = value[1:-1].strip()
            return [] if not inner else [item.strip().strip("\"'") for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in base.items():
        merged[key] = _deep_merge(value, {}) if isinstance(value, dict) else value
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_input_path(config: dict[str, Any], spec: dict[str, Any] | str | None) -> Path | None:
    if not spec:
        return None
    raw = spec if isinstance(spec, str) else spec.get("path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(config["_config_dir"]) / path
    return path
