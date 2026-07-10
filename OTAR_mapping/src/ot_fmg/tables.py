from __future__ import annotations

import csv
import gzip
import json
from json import JSONDecodeError
from pathlib import Path
from collections.abc import Iterator
from typing import Any


Row = dict[str, Any]


def iter_table(path: Path | None) -> Iterator[Row]:
    """Yield rows from one table or all supported tables in a directory.

    Partitioned gzip JSON exports are treated as JSON Lines so large link
    datasets can be filtered without materializing every row in memory.
    """

    if path is None:
        return
    if not path.exists():
        raise FileNotFoundError(f"Input table does not exist: {path}")
    if path.is_dir():
        parts = sorted(part for part in path.iterdir() if part.is_file() and _table_suffix(part))
        if not parts:
            raise ValueError(f"Input directory does not contain supported table files: {path}")
        for part in parts:
            yield from iter_table(part)
        return

    suffix = _table_suffix(path)
    if suffix in {".json", ".jsonl"} and (suffix == ".jsonl" or path.suffix.lower() == ".gz"):
        yield from _iter_json_lines(path)
        return

    yield from read_table(path)


def read_table(path: Path | None) -> list[Row]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Input table does not exist: {path}")

    suffix = _table_suffix(path)
    if suffix == ".csv":
        with _open_text(path, newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".json":
        text = _read_text(path)
        try:
            data = json.loads(text)
        except JSONDecodeError:
            return _read_json_lines(path)
        if isinstance(data, list):
            return [dict(row) for row in data]
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("data")
            if isinstance(rows, list):
                return [dict(row) for row in rows]
        raise ValueError(f"JSON table must be a list or contain rows/data: {path}")
    if suffix == ".jsonl":
        return _read_json_lines(path)
    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("Parquet input requires pandas plus pyarrow or fastparquet") from exc
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            raise RuntimeError(f"Could not read parquet table {path}: {exc}") from exc
        frame = frame.where(pd.notnull(frame), None)
        return [dict(row) for row in frame.to_dict(orient="records")]

    raise ValueError(f"Unsupported table extension for {path}. Use csv, json, jsonl, parquet, or gzipped json/jsonl/csv")


def _read_json_lines(path: Path) -> list[Row]:
    return list(_iter_json_lines(path))


def _iter_json_lines(path: Path) -> Iterator[Row]:
    with _open_text(path) as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON object on line {line_number} of {path}: {exc}") from exc
            if isinstance(value, dict):
                rows = value.get("rows") or value.get("data")
                if isinstance(rows, list):
                    yield from (dict(row) for row in rows)
                else:
                    yield dict(value)
            elif isinstance(value, list):
                yield from (dict(row) for row in value)
            else:
                raise ValueError(f"JSON line {line_number} of {path} must contain an object or list")


def _table_suffix(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    suffix = suffixes[-2] if suffixes[-1:] == [".gz"] and len(suffixes) > 1 else path.suffix.lower()
    return suffix if suffix in {".csv", ".json", ".jsonl", ".parquet"} else ""


def _read_text(path: Path) -> str:
    with _open_text(path) as handle:
        return handle.read()


def _open_text(path: Path, **kwargs: Any):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", **kwargs)
    return path.open(encoding="utf-8", **kwargs)


def merge_metric_rows(
    disease_rows: list[Row],
    metric_rows: list[Row],
    disease_id_col: str,
    metric_disease_id_col: str,
) -> list[Row]:
    metrics_by_id: dict[str, Row] = {}
    for row in metric_rows:
        disease_id = _clean_id(row.get(metric_disease_id_col))
        if disease_id:
            metrics_by_id.setdefault(disease_id, {}).update(row)

    merged: list[Row] = []
    for row in disease_rows:
        disease_id = _clean_id(row.get(disease_id_col))
        combined = dict(row)
        if disease_id in metrics_by_id:
            combined.update(metrics_by_id[disease_id])
        merged.append(combined)
    return merged


def _clean_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
