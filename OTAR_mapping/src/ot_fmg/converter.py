from __future__ import annotations

import ast
import json
import math
import heapq
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .azgaar import MapPayload, build_svg, color_for_id, related_color_for_id, stable_int, write_map
from .config import resolve_input_path
from .ontology import Assignment, OntologyResolver
from .tables import iter_table, merge_metric_rows, read_table


PHASE_RANKS = {
    "UNKNOWN": 0,
    "IND": 0,
    "PRECLINICAL": 0,
    "EARLY_PHASE_1": 1,
    "PHASE_1": 1,
    "PHASE_1_2": 2,
    "PHASE_2": 2,
    "PHASE_2_3": 3,
    "PHASE_3": 3,
    "PREAPPROVAL": 3,
    "PHASE_4": 4,
    "APPROVAL": 4,
    "APPROVED": 4,
}


@dataclass
class RectNode:
    key: str
    rect: tuple[float, float, float, float]
    children: list["RectNode"]

    def find(self, x: float, y: float) -> "RectNode":
        for child in self.children:
            cx, cy, cw, ch = child.rect
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return child.find(x, y)
        return self


@dataclass
class BuildResult:
    map_path: Path
    manifest_path: Path
    disease_count: int
    state_count: int
    province_count: int
    route_count: int
    cell_count: int


def _state_rows_to_tables(
    config: dict[str, Any], spec: dict[str, Any] | str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str], list[str]]:
    options = spec if isinstance(spec, dict) else {}
    rows = read_table(resolve_input_path(config, spec))
    if not rows:
        raise ValueError("No state rows were loaded")

    state_id_col = options.get("state_id", "therapeuticArea")
    state_name_col = options.get("state_name", "therapeuticAreaName")
    province_id_col = options.get("province_id", "provinceId")
    province_name_col = options.get("province_name", "provinceName")
    leaf_id_col = options.get("leaf_id", "leafId")
    leaf_name_col = options.get("leaf_name", "leafName")
    population_col = options.get("population", "populationSize")
    root_id = _clean_id(options.get("root_id", "__OPEN_TARGETS_ROOT__")) or "__OPEN_TARGETS_ROOT__"
    root_name = _clean_name(options.get("root_name", "Open Targets"), "Open Targets")

    disease_by_id: dict[str, dict[str, Any]] = {}
    state_ids_by_leaf: dict[str, set[str]] = defaultdict(set)
    state_names_by_leaf: dict[str, set[str]] = defaultdict(set)
    province_ids_by_leaf: dict[str, set[str]] = defaultdict(set)
    province_names_by_leaf: dict[str, set[str]] = defaultdict(set)
    edges: set[tuple[str, str]] = set()
    names: dict[str, str] = {root_id: root_name}

    for row in rows:
        leaf_id = _clean_id(row.get(leaf_id_col))
        state_id = _clean_id(row.get(state_id_col))
        province_id = _clean_id(row.get(province_id_col))
        if not leaf_id or not state_id or not province_id:
            continue

        leaf_name = _clean_name(row.get(leaf_name_col), leaf_id)
        state_name = _clean_name(row.get(state_name_col), state_id)
        province_name = _clean_name(row.get(province_name_col), province_id)
        population = _float(row.get(population_col), 0.0)

        disease = disease_by_id.setdefault(
            leaf_id,
            {
                "disease_id": leaf_id,
                "disease_name": leaf_name,
                "populationSize": population,
                "populationSizeTotal": 0.0,
                "membershipCount": 0,
            },
        )
        if leaf_name and (not disease.get("disease_name") or leaf_name < disease["disease_name"]):
            disease["disease_name"] = leaf_name
        disease["populationSize"] = max(_float(disease.get("populationSize"), 0.0), population)
        disease["populationSizeTotal"] = _float(disease.get("populationSizeTotal"), 0.0) + population
        disease["membershipCount"] = int(disease.get("membershipCount") or 0) + 1

        state_ids_by_leaf[leaf_id].add(state_id)
        state_names_by_leaf[leaf_id].add(state_name)
        province_ids_by_leaf[leaf_id].add(province_id)
        province_names_by_leaf[leaf_id].add(province_name)

        names.setdefault(state_id, state_name)
        names.setdefault(province_id, province_name)
        names.setdefault(leaf_id, leaf_name)
        edges.add((state_id, root_id))
        edges.add((province_id, state_id))
        edges.add((leaf_id, province_id))

    if not disease_by_id:
        raise ValueError(
            "State rows did not contain any complete leaf/state/province records. "
            f"Expected columns like {leaf_id_col!r}, {state_id_col!r}, and {province_id_col!r}."
        )

    disease_rows: list[dict[str, Any]] = []
    for leaf_id in sorted(disease_by_id):
        row = disease_by_id[leaf_id]
        row["stateIds"] = "|".join(sorted(state_ids_by_leaf[leaf_id]))
        row["stateNames"] = "|".join(sorted(state_names_by_leaf[leaf_id]))
        row["provinceIds"] = "|".join(sorted(province_ids_by_leaf[leaf_id]))
        row["provinceNames"] = "|".join(sorted(province_names_by_leaf[leaf_id]))
        disease_rows.append(row)

    ontology_rows = [
        {"child_id": child_id, "parent_id": parent_id}
        for child_id, parent_id in sorted(edges, key=lambda item: (item[1], item[0]))
    ]
    return disease_rows, ontology_rows, names, [root_id]


def _with_state_rows_defaults(config: dict[str, Any], root_ids: list[str]) -> dict[str, Any]:
    updated = dict(config)
    ontology = dict(config.get("ontology", {}))
    merged_roots = list(ontology.get("root_ids") or [])
    for root_id in root_ids:
        if root_id not in merged_roots:
            merged_roots.append(root_id)
    ontology["root_ids"] = merged_roots
    updated["ontology"] = ontology

    layers = dict(config.get("layers", {}))
    state_row_defaults = {
        "elevation": "populationSizeTotal",
        "precipitation": "membershipCount",
        "biome": "populationSize",
        "population": "populationSizeTotal",
    }
    for key, value in state_row_defaults.items():
        if not layers.get(key):
            layers[key] = value
    updated["layers"] = layers
    return updated


def build_map(config: dict[str, Any], out_path: Path, manifest_path: Path | None = None) -> BuildResult:
    inputs = config.get("inputs", {})
    state_rows_spec = inputs.get("state_rows")
    disease_spec = inputs.get("diseases", {})
    ontology_spec = inputs.get("ontology", {})
    metric_spec = inputs.get("metrics", {})
    link_spec = inputs.get("links", {})
    flat_names: dict[str, str] = {}
    flat_root_ids: list[str] = []

    if state_rows_spec:
        disease_rows, ontology_rows, flat_names, flat_root_ids = _state_rows_to_tables(config, state_rows_spec)
        disease_spec = {"id": "disease_id", "name": "disease_name"}
        ontology_spec = {"child": "child_id", "parent": "parent_id"}
        config = _with_state_rows_defaults(config, flat_root_ids)
    else:
        disease_rows = read_table(resolve_input_path(config, disease_spec))
        ontology_rows = read_table(resolve_input_path(config, ontology_spec))

    if not disease_rows:
        raise ValueError("No diseases were loaded")

    disease_id_col = disease_spec.get("id", "disease_id")
    disease_name_col = disease_spec.get("name", "disease_name")
    metric_rows = read_table(resolve_input_path(config, metric_spec))
    if metric_rows:
        metric_id_col = metric_spec.get("disease_id", disease_id_col)
        disease_rows = merge_metric_rows(disease_rows, metric_rows, disease_id_col, metric_id_col)

    disease_rows_by_id: dict[str, dict[str, Any]] = {}
    disease_names: dict[str, str] = {}
    for row in disease_rows:
        disease_id = _clean_id(row.get(disease_id_col))
        if not disease_id:
            continue
        disease_rows_by_id[disease_id] = row
        disease_names[disease_id] = str(row.get(disease_name_col) or disease_id)
    disease_ids = sorted(disease_rows_by_id)
    if len(disease_ids) >= 65536:
        raise ValueError("Azgaar stores burg ids in Uint16Array; v1 supports at most 65,535 diseases")

    disease_names.update({key: value for key, value in flat_names.items() if value})
    child_col = ontology_spec.get("child", "child_id")
    parent_col = ontology_spec.get("parent", "parent_id")
    for row in ontology_rows:
        for col in (child_col, parent_col):
            value = _clean_id(row.get(col))
            if value and value not in disease_names:
                disease_names[value] = value

    ontology_config = config.get("ontology", {})
    resolver = OntologyResolver(
        disease_ids,
        ontology_rows,
        child_col,
        parent_col,
        root_ids=ontology_config.get("root_ids") or [],
        skip_roots=bool(ontology_config.get("skip_roots", True)),
    )
    assignments = resolver.assign_all()

    state_keys = sorted({assignment.state_id for assignment in assignments.values()})
    state_id_by_key = {key: i + 1 for i, key in enumerate(state_keys)}
    province_keys_by_state: dict[str, list[str]] = {}
    for state_key in state_keys:
        province_keys_by_state[state_key] = sorted(
            {a.province_id for a in assignments.values() if a.state_id == state_key}
        )

    province_id_by_key: dict[str, int] = {}
    next_province_id = 1
    for state_key in state_keys:
        for province_key in province_keys_by_state[state_key]:
            province_id_by_key[province_key] = next_province_id
            next_province_id += 1

    map_config = config.get("map", {})
    width = int(map_config.get("width") or 2600)
    height = int(map_config.get("height") or 1600)
    max_cells = int(map_config.get("max_cells") or 100000)
    requested_cells = map_config.get("cells")
    if requested_cells:
        cell_count_target = int(requested_cells)
    else:
        cell_multiplier = float(map_config.get("cell_multiplier") or 4.0)
        cell_count_target = min(max_cells, max(1000, math.ceil(len(disease_ids) * cell_multiplier)))
    cell_count_target = max(cell_count_target, len(disease_ids))
    if cell_count_target > max_cells:
        raise ValueError(f"Requested {cell_count_target} cells exceeds max_cells={max_cells}")

    grid = _generate_grid(width, height, cell_count_target, max_cells, min_cells=len(disease_ids))
    points = grid["points"]
    cell_count = len(points)
    if cell_count < len(disease_ids):
        raise ValueError(f"Generated {cell_count} cells but need {len(disease_ids)} disease cells")

    state_weights = [(key, sum(1 for assignment in assignments.values() if assignment.state_id == key)) for key in state_keys]
    state_tree = RectNode("root", (0.0, 0.0, float(width), float(height)), _split_rects(state_weights, (0.0, 0.0, float(width), float(height))))
    province_trees: dict[str, RectNode] = {}
    for state_node in state_tree.children:
        province_weights = [
            (province_key, sum(1 for a in assignments.values() if a.state_id == state_node.key and a.province_id == province_key))
            for province_key in province_keys_by_state[state_node.key]
        ]
        state_node.children = _split_rects(province_weights, state_node.rect)
        province_trees[state_node.key] = state_node

    state_rects = {state_id_by_key[node.key]: node.rect for node in state_tree.children}
    province_rects: dict[int, tuple[float, float, float, float]] = {}
    for state_node in state_tree.children:
        for province_node in state_node.children:
            province_rects[province_id_by_key[province_node.key]] = province_node.rect

    disease_cell: dict[str, int] = {}
    used_cells: set[int] = set()
    diseases_by_province: dict[int, list[str]] = defaultdict(list)
    for disease_id, assignment in assignments.items():
        diseases_by_province[province_id_by_key[assignment.province_id]].append(disease_id)

    state_weight_by_id = {
        state_id_by_key[key]: sum(1 for assignment in assignments.values() if assignment.state_id == key)
        for key in state_keys
    }
    state_seed_points = _seed_region_points(points, list(range(cell_count)), state_weight_by_id, "state")
    state_assignment = _assign_expanded_regions(
        points,
        grid,
        list(range(cell_count)),
        state_weight_by_id,
        state_seed_points,
        "state",
    )
    cell_state = [state_assignment.get(i, 0) for i in range(cell_count)]

    cell_province = [0] * cell_count
    available_by_province: dict[int, list[int]] = defaultdict(list)
    for state_key in state_keys:
        state_id = state_id_by_key[state_key]
        allowed_cells = [cell for cell, assigned_state in enumerate(cell_state) if assigned_state == state_id]
        if not allowed_cells:
            continue
        province_weight_by_id = {
            province_id_by_key[province_key]: len(diseases_by_province[province_id_by_key[province_key]])
            for province_key in province_keys_by_state[state_key]
        }
        province_seed_points = _seed_region_points(points, allowed_cells, province_weight_by_id, f"province:{state_id}")
        province_assignment = _assign_expanded_regions(
            points,
            grid,
            allowed_cells,
            province_weight_by_id,
            province_seed_points,
            f"province:{state_id}",
        )
        for cell, province_id in province_assignment.items():
            cell_province[cell] = province_id
            available_by_province[province_id].append(cell)

    for province_id, ids in sorted(diseases_by_province.items()):
        ids.sort()
        candidates = sorted(available_by_province.get(province_id, []), key=lambda i: (points[i][1], points[i][0]))
        if sum(1 for cell in candidates if cell not in used_cells) < len(ids):
            province_state_id = state_id_by_key[assignments[ids[0]].state_id]
            state_cells = [cell for cell, assigned_state in enumerate(cell_state) if assigned_state == province_state_id]
            candidates = _expand_candidates(candidates, province_rects[province_id], points, used_cells, allowed_cells=state_cells)
        chosen = _natural_pick(candidates, ids, used_cells, points, f"province:{province_id}")
        if len(chosen) < len(ids):
            raise ValueError(f"Province {province_id} has insufficient free cells for {len(ids)} diseases")
        for disease_id, cell in zip(ids, chosen):
            assignment = assignments[disease_id]
            cell_state[cell] = state_id_by_key[assignment.state_id]
            cell_province[cell] = province_id
            disease_cell[disease_id] = cell
            used_cells.add(cell)

    layers = config.get("layers", {})
    elevation_metric = layers.get("elevation")
    precipitation_metric = layers.get("precipitation")
    temperature_metric = layers.get("temperature")
    phase_drug_count_metric = layers.get("phase_drug_count")
    biome_metric = layers.get("biome")
    population_metric = layers.get("population")
    religion_metric = layers.get("religion")
    good_metric = layers.get("good")

    if phase_drug_count_metric:
        elevation_by_disease = _scaled_present_metric(
            disease_rows_by_id, disease_ids, elevation_metric, 35, 90, missing=24, default=24
        )
        precipitation_by_disease, phase_by_disease = _phase_precipitation_metric(
            disease_rows_by_id, disease_ids, precipitation_metric, phase_drug_count_metric
        )
    else:
        elevation_by_disease = _scaled_metric(disease_rows_by_id, disease_ids, elevation_metric, 24, 90, default=45)
        precipitation_by_disease = _scaled_metric(disease_rows_by_id, disease_ids, precipitation_metric, 5, 100, default=30)
        phase_by_disease = {disease_id: 0 for disease_id in disease_ids}
    temperature_by_disease = _scaled_present_metric(
        disease_rows_by_id, disease_ids, temperature_metric, 2, 42, missing=0, default=12
    )
    population_by_disease = _scaled_metric(disease_rows_by_id, disease_ids, population_metric, 0.15, 12.0, default=1.0)
    biome_by_disease = _biome_metric(disease_rows_by_id, disease_ids, biome_metric)
    religion_by_disease, religions = _categorical_layer(disease_rows_by_id, disease_ids, religion_metric, "No religion")
    good_by_disease, goods = _goods_layer(disease_rows_by_id, disease_ids, good_metric)

    province_elevation = _province_average(diseases_by_province, elevation_by_disease, default=45)
    province_precipitation = {} if phase_drug_count_metric else _province_average(
        diseases_by_province, precipitation_by_disease, default=30
    )
    province_temperature = {} if phase_drug_count_metric else _province_average(
        diseases_by_province, temperature_by_disease, default=12
    )
    province_biome = _province_mode(diseases_by_province, biome_by_disease, default=6)
    province_religion = _province_mode(diseases_by_province, religion_by_disease, default=0)
    province_good = _province_mode(diseases_by_province, good_by_disease, default=0)

    grid_h = [int(province_elevation.get(cell_province[i], 45)) for i in range(cell_count)]
    grid_prec_default = 0 if phase_drug_count_metric else 30
    grid_prec = [int(province_precipitation.get(cell_province[i], grid_prec_default)) for i in range(cell_count)]
    grid_f = [1] * cell_count
    grid_t = [2] * cell_count
    grid_temp_default = 0 if phase_drug_count_metric else 12
    grid_temp = [int(province_temperature.get(cell_province[i], grid_temp_default)) for i in range(cell_count)]

    cell_biome = [int(province_biome.get(cell_province[i], 6)) for i in range(cell_count)]
    cell_burg = [0] * cell_count
    cell_conf = [0] * cell_count
    cell_culture = [1 if cell_state[i] else 0 for i in range(cell_count)]
    cell_fl = [0] * cell_count
    cell_pop = [0.01 if cell_state[i] else 0 for i in range(cell_count)]
    cell_r = [0] * cell_count
    cell_s = [10 if cell_state[i] else 0 for i in range(cell_count)]
    cell_religion = [int(province_religion.get(cell_province[i], 0)) for i in range(cell_count)]
    cell_good = [int(province_good.get(cell_province[i], 0)) for i in range(cell_count)]
    cell_market = [0] * cell_count

    for disease_id, cell in disease_cell.items():
        grid_h[cell] = int(elevation_by_disease[disease_id])
        grid_prec[cell] = int(precipitation_by_disease[disease_id])
        grid_temp[cell] = int(temperature_by_disease[disease_id])
        cell_biome[cell] = int(biome_by_disease[disease_id])
        cell_religion[cell] = int(religion_by_disease[disease_id])
        cell_good[cell] = int(good_by_disease[disease_id])
        cell_pop[cell] = float(population_by_disease[disease_id])
        cell_s[cell] = 100

    burgs: list[Any] = [0]
    burg_id_by_disease: dict[str, int] = {}
    state_first_burg: dict[int, int] = {}
    province_first_burg: dict[int, int] = {}
    burg_percentile_by_disease = _rank_percentiles(population_by_disease, disease_ids)
    for burg_id, disease_id in enumerate(disease_ids, start=1):
        assignment = assignments[disease_id]
        state_id = state_id_by_key[assignment.state_id]
        province_id = province_id_by_key[assignment.province_id]
        cell = disease_cell[disease_id]
        x, y = _burg_point(cell, disease_id, grid, width, height)
        burg_id_by_disease[disease_id] = burg_id
        state_first_burg.setdefault(state_id, burg_id)
        province_first_burg.setdefault(province_id, burg_id)
        cell_burg[cell] = burg_id
        burgs.append(
            {
                "cell": cell,
                "x": round(x, 2),
                "y": round(y, 2),
                "i": burg_id,
                "state": state_id,
                "province": province_id,
                "culture": 1,
                "name": disease_names.get(disease_id, disease_id),
                "feature": 1,
                "capital": 0,
                "port": 0,
                "population": round(float(population_by_disease[disease_id]), 4),
                "type": "Generic",
                "group": _burg_group(burg_percentile_by_disease[disease_id]),
                "coa": {},
                "lock": True,
                "market": 0,
                "product": 0,
                "treasury": 0,
                "production": [],
            }
        )
    for state_id, burg_id in state_first_burg.items():
        burgs[burg_id]["capital"] = 1
        burgs[burg_id]["group"] = "capital"

    cell_area = width * height / cell_count
    state_stats = _summarize_regions(cell_state, cell_pop, cell_burg, burgs, cell_area)
    province_stats = _summarize_regions(cell_province, cell_pop, cell_burg, burgs, cell_area)
    state_poles = _region_poles(cell_state, grid)
    province_poles = _region_poles(cell_province, grid)

    states: list[dict[str, Any]] = [_neutral_state(len(state_keys))]
    for state_key in state_keys:
        state_id = state_id_by_key[state_key]
        x, y, w, h = state_rects[state_id]
        stats = state_stats[state_id]
        state_name = disease_names.get(state_key, state_key)
        states.append(
            {
                "i": state_id,
                "name": state_name,
                "form": "Union",
                "formName": "State",
                "fullName": f"{state_name} State",
                "color": color_for_id(state_key),
                "center": burgs[state_first_burg[state_id]]["cell"],
                "pole": state_poles.get(state_id, [round(x + w / 2, 2), round(y + h / 2, 2)]),
                "culture": 1,
                "type": "Generic",
                "expansionism": 1,
                "area": round(stats["area"], 2),
                "burgs": stats["burgs"],
                "cells": stats["cells"],
                "rural": round(stats["rural"], 4),
                "urban": round(stats["urban"], 4),
                "neighbors": [],
                "provinces": [province_id_by_key[p] for p in province_keys_by_state[state_key]],
                "diplomacy": [],
                "campaigns": [],
                "alert": 0,
                "military": [],
                "coa": {},
                "salesTax": 0,
                "pollTax": 0,
                "treasury": 0,
                "lock": True,
            }
        )
    diplomacy = ["x"] * len(states)
    for state in states:
        state["diplomacy"] = diplomacy.copy()

    provinces: list[Any] = [0]
    province_key_by_id = {value: key for key, value in province_id_by_key.items()}
    state_color_by_id = {state["i"]: state["color"] for state in states[1:] if isinstance(state, dict)}
    province_index_by_key = {
        province_key: index
        for province_keys in province_keys_by_state.values()
        for index, province_key in enumerate(province_keys)
    }
    province_count_by_state_key = {state_key: len(province_keys) for state_key, province_keys in province_keys_by_state.items()}
    for province_id in range(1, len(province_key_by_id) + 1):
        province_key = province_key_by_id[province_id]
        assignment_for_province = next(a for a in assignments.values() if a.province_id == province_key)
        state_id = state_id_by_key[assignment_for_province.state_id]
        x, y, w, h = province_rects[province_id]
        stats = province_stats[province_id]
        province_name = disease_names.get(province_key, province_key)
        provinces.append(
            {
                "i": province_id,
                "state": state_id,
                "name": province_name,
                "formName": "Province",
                "fullName": f"{province_name} Province",
                "color": related_color_for_id(
                    state_color_by_id[state_id],
                    province_key,
                    index=province_index_by_key[province_key],
                    count=province_count_by_state_key[assignment_for_province.state_id],
                ),
                "center": burgs[province_first_burg[province_id]]["cell"],
                "pole": province_poles.get(province_id, [round(x + w / 2, 2), round(y + h / 2, 2)]),
                "area": round(stats["area"], 2),
                "burg": province_first_burg[province_id],
                "burgs": [burg_id_by_disease[d] for d in sorted(diseases_by_province[province_id])],
                "cells": stats["cells"],
                "rural": round(stats["rural"], 4),
                "urban": round(stats["urban"], 4),
                "coa": {},
                "lock": True,
            }
        )

    cultures = [
        {"name": "Wildlands", "i": 0, "base": 1, "origins": [None], "shield": "round", "type": "Generic"},
        {
            "name": "Diseases",
            "i": 1,
            "base": 1,
            "origins": [0],
            "shield": "round",
            "type": "Generic",
            "center": burgs[1]["cell"] if len(burgs) > 1 else 0,
            "color": "#8b1e3f",
            "cells": cell_count,
            "area": width * height,
            "rural": round(sum(cell_pop), 4),
            "urban": round(sum(float(b.get("population", 0)) for b in burgs[1:] if isinstance(b, dict)), 4),
        },
    ]

    link_rows = iter_table(resolve_input_path(config, link_spec))
    max_routes_value = map_config.get("max_routes")
    max_routes = int(max_routes_value) if max_routes_value is not None else 0
    routes, cell_routes = _build_routes(
        link_rows,
        link_spec.get("source", "source_id") if isinstance(link_spec, dict) else "source_id",
        link_spec.get("target", "target_id") if isinstance(link_spec, dict) else "target_id",
        link_spec.get("weight", "weight") if isinstance(link_spec, dict) else "weight",
        burg_id_by_disease,
        burgs,
        max_routes=max_routes,
        min_weight=(
            _float(link_spec.get("min_weight"), 0.0)
            if isinstance(link_spec, dict)
            else 0.0
        ),
    )

    notes = _build_notes(config, disease_ids, assignments, disease_names, disease_rows_by_id, burg_id_by_disease)
    features = [
        0,
        {
            "i": 1,
            "type": "island",
            "land": True,
            "border": True,
            "cells": cell_count,
            "firstCell": 0,
            "vertices": [],
            "area": width * height,
            "shoreline": [],
            "height": 45,
            "group": "continent",
        },
    ]
    grid_general = {
        "spacing": grid["spacing"],
        "cellsX": grid["cellsX"],
        "cellsY": grid["cellsY"],
        "boundary": grid["boundary"],
        "points": points,
        "features": features,
        "cellsDesired": grid["cellsDesired"],
    }

    svg_config = config.get("svg", {})
    max_burg_icons = svg_config.get("max_burg_icons")
    if max_burg_icons is None:
        max_burg_icons = 50000

    svg = build_svg(
        width,
        height,
        states,
        provinces,
        burgs,
        routes,
        state_rects,
        province_rects,
        grid,
        cell_state,
        cell_province,
        max_burg_icons=int(max_burg_icons),
        shape_rendering=str(svg_config.get("shape_rendering") or "optimizeSpeed"),
        render_state_fill=bool(svg_config.get("state_fill")),
        render_state_halo=bool(svg_config.get("state_halo")),
        render_province_labels=bool(svg_config.get("province_labels")),
        render_cells_layer=bool(svg_config.get("cells_layer")),
        clip_to_land=bool(svg_config.get("clip_to_land")),
    )
    seed = int(map_config.get("seed") or stable_int(str(out_path)))
    payload = MapPayload(
        name=str(map_config.get("name") or "Open Targets Atlas"),
        version=str(map_config.get("version") or "1.134.2"),
        seed=seed,
        map_id=int(map_config.get("map_id") or stable_int(f"{out_path}:map")),
        width=width,
        height=height,
        grid_general=grid_general,
        grid_h=grid_h,
        grid_prec=grid_prec,
        grid_f=grid_f,
        grid_t=grid_t,
        grid_temp=grid_temp,
        features=features,
        cultures=cultures,
        states=states,
        burgs=burgs,
        cell_biome=cell_biome,
        cell_burg=cell_burg,
        cell_conf=cell_conf,
        cell_culture=cell_culture,
        cell_fl=cell_fl,
        cell_pop=cell_pop,
        cell_r=cell_r,
        cell_s=cell_s,
        cell_state=cell_state,
        cell_religion=cell_religion,
        cell_province=cell_province,
        religions=religions,
        provinces=provinces,
        cell_routes=cell_routes,
        routes=routes,
        cell_good=cell_good,
        goods=goods,
        cell_market=cell_market,
        notes=notes,
        svg=svg,
        style_preset=str(map_config.get("style") or "ancient"),
    )
    write_map(payload, out_path)

    manifest_path = manifest_path or out_path.with_suffix(".manifest.json")
    _write_manifest(
        manifest_path,
        disease_ids,
        assignments,
        disease_names,
        state_id_by_key,
        province_id_by_key,
        burg_id_by_disease,
        routes,
        states,
        provinces,
    )

    return BuildResult(
        map_path=out_path,
        manifest_path=manifest_path,
        disease_count=len(disease_ids),
        state_count=len(states) - 1,
        province_count=len(provinces) - 1,
        route_count=len(routes),
        cell_count=cell_count,
    )


def _generate_grid(
    width: int,
    height: int,
    target: int,
    max_cells: int,
    *,
    min_cells: int | None = None,
) -> dict[str, Any]:
    min_cells = max(1, min_cells if min_cells is not None else target)
    if min_cells > max_cells:
        raise ValueError(f"Cannot generate {min_cells} required cells within max_cells={max_cells}")

    desired = max(target, min_cells)
    spacing = round(math.sqrt((width * height) / max(desired, 1)), 2)
    cells_x, cells_y, count = _grid_shape(width, height, spacing)

    while count > max_cells:
        spacing = round(spacing + 0.01, 2)
        cells_x, cells_y, count = _grid_shape(width, height, spacing)

    while count < min_cells:
        spacing = round(max(0.01, spacing - 0.01), 2)
        cells_x, cells_y, count = _grid_shape(width, height, spacing)
        if count > max_cells:
            raise ValueError(f"Cannot generate {min_cells} required cells within max_cells={max_cells}")

    radius = spacing / 2
    jittering = radius * 0.9
    points: list[list[float]] = []
    for row in range(cells_y):
        y0 = radius + row * spacing
        for col in range(cells_x):
            x0 = radius + col * spacing
            jitter_x = (_hash_unit(f"grid:x:{row}:{col}") * 2 - 1) * jittering
            jitter_y = (_hash_unit(f"grid:y:{row}:{col}") * 2 - 1) * jittering
            x = min(width, max(0, x0 + jitter_x))
            y = min(height, max(0, y0 + jitter_y))
            points.append([round(x, 2), round(y, 2)])

    boundary = _boundary_points(width, height, spacing)
    return {
        "cellsX": cells_x,
        "cellsY": cells_y,
        "cellWidth": spacing,
        "cellHeight": spacing,
        "spacing": spacing,
        "points": points,
        "boundary": boundary,
        "cellsDesired": target,
    }


def _region_poles(regions: list[int], grid: dict[str, Any]) -> dict[int, list[float]]:
    """Find a stable interior label point for every non-zero grid region."""

    cells_x = int(grid["cellsX"])
    cells_y = int(grid["cellsY"])
    points = grid["points"]
    cells_by_region: dict[int, list[int]] = defaultdict(list)
    for cell, region_id in enumerate(regions):
        if region_id:
            cells_by_region[int(region_id)].append(cell)

    poles: dict[int, list[float]] = {}
    for region_id, region_cells in cells_by_region.items():
        remaining = set(region_cells)
        components: list[list[int]] = []
        while remaining:
            start = min(remaining)
            remaining.remove(start)
            component = [start]
            queue = [start]
            while queue:
                cell = queue.pop()
                for neighbor in _grid_neighbors(cell, cells_x, cells_y):
                    if neighbor not in remaining:
                        continue
                    remaining.remove(neighbor)
                    component.append(neighbor)
                    queue.append(neighbor)
            components.append(component)

        component = max(components, key=lambda cells: (len(cells), -min(cells)))
        component_set = set(component)
        distance = {cell: -1 for cell in component}
        boundary: deque[int] = deque()
        for cell in component:
            row, col = divmod(cell, cells_x)
            neighbors = _grid_neighbors(cell, cells_x, cells_y)
            is_map_edge = row == 0 or row == cells_y - 1 or col == 0 or col == cells_x - 1
            if is_map_edge or any(neighbor not in component_set for neighbor in neighbors):
                distance[cell] = 0
                boundary.append(cell)

        while boundary:
            cell = boundary.popleft()
            for neighbor in _grid_neighbors(cell, cells_x, cells_y):
                if neighbor not in component_set or distance[neighbor] >= 0:
                    continue
                distance[neighbor] = distance[cell] + 1
                boundary.append(neighbor)

        centroid_x = sum(float(points[cell][0]) for cell in component) / len(component)
        centroid_y = sum(float(points[cell][1]) for cell in component) / len(component)
        pole_cell = max(
            component,
            key=lambda cell: (
                distance[cell],
                -((float(points[cell][0]) - centroid_x) ** 2 + (float(points[cell][1]) - centroid_y) ** 2),
                -cell,
            ),
        )
        poles[region_id] = [round(float(points[pole_cell][0]), 2), round(float(points[pole_cell][1]), 2)]
    return poles


def _grid_neighbors(cell: int, cells_x: int, cells_y: int) -> list[int]:
    row, col = divmod(cell, cells_x)
    neighbors: list[int] = []
    if col:
        neighbors.append(cell - 1)
    if col + 1 < cells_x:
        neighbors.append(cell + 1)
    if row:
        neighbors.append(cell - cells_x)
    if row + 1 < cells_y:
        neighbors.append(cell + cells_x)
    return neighbors


def _grid_shape(width: int, height: int, spacing: float) -> tuple[int, int, int]:
    cells_x = max(1, math.floor((width + 0.5 * spacing - 1e-10) / spacing))
    cells_y = max(1, math.floor((height + 0.5 * spacing - 1e-10) / spacing))
    return cells_x, cells_y, cells_x * cells_y


def _boundary_points(width: int, height: int, spacing: float) -> list[list[float]]:
    offset = round(-spacing, 2)
    boundary_spacing = spacing * 2
    extended_width = width - offset * 2
    extended_height = height - offset * 2
    count_x = max(1, math.ceil(extended_width / boundary_spacing) - 1)
    count_y = max(1, math.ceil(extended_height / boundary_spacing) - 1)
    points: list[list[float]] = []

    for index in range(count_x):
        i = index + 0.5
        x = math.ceil((extended_width * i) / count_x + offset)
        points.append([x, offset])
        points.append([x, round(extended_height + offset, 2)])

    for index in range(count_y):
        i = index + 0.5
        y = math.ceil((extended_height * i) / count_y + offset)
        points.append([offset, y])
        points.append([round(extended_width + offset, 2), y])

    return points


def _split_rects(items: list[tuple[str, int]], rect: tuple[float, float, float, float]) -> list[RectNode]:
    items = [(key, max(1, int(weight))) for key, weight in items]
    if not items:
        return []
    if len(items) == 1:
        return [RectNode(items[0][0], rect, [])]

    total = sum(weight for _, weight in items)
    left: list[tuple[str, int]] = []
    running = 0
    for item in items:
        if left and running + item[1] > total / 2:
            break
        left.append(item)
        running += item[1]
    right = items[len(left) :]
    if not right:
        right = [left.pop()]
        running = sum(weight for _, weight in left)

    x, y, w, h = rect
    ratio = running / total
    if w >= h:
        left_rect = (x, y, w * ratio, h)
        right_rect = (x + w * ratio, y, w * (1 - ratio), h)
    else:
        left_rect = (x, y, w, h * ratio)
        right_rect = (x, y + h * ratio, w, h * (1 - ratio))
    return _split_rects(left, left_rect) + _split_rects(right, right_rect)


def _spread_pick(candidates: list[int], count: int, used: set[int]) -> list[int]:
    if count <= 0:
        return []
    free = [cell for cell in candidates if cell not in used]
    if len(free) <= count:
        return free
    picked: list[int] = []
    for index in range(count):
        position = round((index + 0.5) * len(free) / count - 0.5)
        position = min(len(free) - 1, max(0, position))
        while free[position] in picked and position + 1 < len(free):
            position += 1
        picked.append(free[position])
    return picked


def _natural_pick(
    candidates: list[int],
    disease_ids: list[str],
    used: set[int],
    points: list[list[float]],
    seed: str,
) -> list[int]:
    count = len(disease_ids)
    if count <= 0:
        return []
    free = [cell for cell in candidates if cell not in used]
    if len(free) <= count:
        return sorted(free, key=lambda cell: _hash_unit(f"{seed}:fallback:{cell}"))

    xs = [points[cell][0] for cell in free]
    ys = [points[cell][1] for cell in free]
    area = max((max(xs) - min(xs)) * (max(ys) - min(ys)), 1)
    spacing = max(1.0, math.sqrt(area / count) * 0.38)
    attractors = _attractor_points(free, points, seed)

    def score(cell: int) -> float:
        x, y = points[cell]
        clustered = 0.0
        for index, (ax, ay, radius) in enumerate(attractors):
            distance2 = (x - ax) ** 2 + (y - ay) ** 2
            clustered += math.exp(-distance2 / max(radius * radius, 1.0)) * (1.15 - index * 0.18)
        return clustered + _hash_unit(f"{seed}:score:{cell}") * 1.35

    ordered = sorted(
        free,
        key=lambda cell: (
            -score(cell),
            points[cell][1],
            points[cell][0],
        ),
    )

    picked: list[int] = []
    picked_set: set[int] = set()
    for _ in range(8):
        index = _SpacingIndex(points, max(spacing, 1.0), picked)
        for cell in ordered:
            if cell in picked_set:
                continue
            local_spacing = spacing * (0.24 + _hash_unit(f"{seed}:spacing:{cell}") * 1.25)
            if not index.is_far_enough(cell, local_spacing):
                continue
            picked.append(cell)
            picked_set.add(cell)
            index.add(cell)
            if len(picked) == count:
                return picked
        spacing *= 0.68

    for cell in ordered:
        if cell in picked_set:
            continue
        picked.append(cell)
        if len(picked) == count:
            break
    return picked


class _SpacingIndex:
    def __init__(self, points: list[list[float]], spacing: float, initial: list[int] | None = None) -> None:
        self.points = points
        self.spacing = max(spacing, 1.0)
        self.buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for cell in initial or []:
            self.add(cell)

    def _bucket(self, cell: int) -> tuple[int, int]:
        x, y = self.points[cell]
        return int(x // self.spacing), int(y // self.spacing)

    def add(self, cell: int) -> None:
        self.buckets[self._bucket(cell)].append(cell)

    def is_far_enough(self, cell: int, spacing: float | None = None) -> bool:
        x, y = self.points[cell]
        bx, by = self._bucket(cell)
        radius = max(float(spacing) if spacing is not None else self.spacing, 1.0)
        min_distance2 = radius * radius
        reach = max(1, int(math.ceil(radius / self.spacing)) + 1)
        for nx in range(bx - reach, bx + reach + 1):
            for ny in range(by - reach, by + reach + 1):
                for other in self.buckets.get((nx, ny), []):
                    ox, oy = self.points[other]
                    if (x - ox) ** 2 + (y - oy) ** 2 < min_distance2:
                        return False
        return True


def _burg_point(cell: int, _disease_id: str, grid: dict[str, Any], _width: int, _height: int) -> tuple[float, float]:
    x, y = grid["points"][cell]
    return round(float(x), 2), round(float(y), 2)


def _expand_candidates(
    candidates: list[int],
    rect: tuple[float, float, float, float],
    points: list[list[float]],
    used: set[int],
    *,
    allowed_cells: list[int] | None = None,
) -> list[int]:
    x, y, w, h = rect
    center = (x + w / 2, y + h / 2)
    expanded = list(dict.fromkeys(candidates))
    pool = allowed_cells if allowed_cells is not None else list(range(len(points)))
    expanded.extend(
        sorted(
            (i for i in pool if i not in used and i not in expanded),
            key=lambda i: (points[i][0] - center[0]) ** 2 + (points[i][1] - center[1]) ** 2,
        )
    )
    return expanded


def _seed_region_points(
    points: list[list[float]],
    cells: list[int],
    weights: dict[int, int],
    seed: str,
) -> dict[int, tuple[float, float]]:
    region_ids = [region_id for region_id in sorted(weights, key=lambda item: (-weights[item], item)) if weights[region_id] > 0]
    if not cells or not region_ids:
        return {}

    xs = [points[cell][0] for cell in cells]
    ys = [points[cell][1] for cell in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    area = max((max_x - min_x) * (max_y - min_y), 1.0)
    spacing = max(1.0, math.sqrt(area / len(region_ids)) * 0.62)
    used_cells: set[int] = set()
    picked: dict[int, tuple[float, float]] = {}

    for region_id in region_ids:
        weight_rank = weights[region_id] / max(max(weights.values()), 1)

        def score(cell: int) -> tuple[float, float, float]:
            x, y = points[cell]
            center_bias = 1 - min(1.0, math.hypot(x - center_x, y - center_y) / max(max_x - min_x, max_y - min_y, 1))
            noise = _hash_unit(f"{seed}:region-seed:{region_id}:{cell}")
            return (noise * 1.65 + center_bias * (0.65 + weight_rank), -y, -x)

        ordered = sorted((cell for cell in cells if cell not in used_cells), key=score, reverse=True)
        local_spacing = spacing
        chosen = ordered[0]
        while local_spacing >= 1:
            for cell in ordered:
                x, y = points[cell]
                if all((x - points[other][0]) ** 2 + (y - points[other][1]) ** 2 >= local_spacing * local_spacing for other in used_cells):
                    chosen = cell
                    break
            else:
                local_spacing *= 0.7
                continue
            break
        used_cells.add(chosen)
        picked[region_id] = (points[chosen][0], points[chosen][1])

    return picked


def _assign_expanded_regions(
    points: list[list[float]],
    grid: dict[str, Any],
    cells: list[int],
    weights: dict[int, int],
    seed_points: dict[int, tuple[float, float]],
    seed: str,
) -> dict[int, int]:
    region_ids = [region_id for region_id in sorted(weights) if weights[region_id] > 0]
    if not cells or not region_ids:
        return {}

    return _assign_voronoi_regions(points, cells, weights, seed_points, seed)


def _assign_voronoi_regions(
    points: list[list[float]],
    cells: list[int],
    weights: dict[int, int],
    seed_points: dict[int, tuple[float, float]],
    seed: str,
) -> dict[int, int]:
    region_ids = [region_id for region_id in sorted(weights) if weights[region_id] > 0]
    targets = _region_cell_targets(region_ids, weights, len(cells))
    remaining = dict(targets)
    assignments: dict[int, int] = {}
    preferences: dict[int, list[tuple[float, int]]] = {}
    heap: list[tuple[float, int, int, int, int]] = []
    serial = 0
    mean_target = sum(targets.values()) / len(targets)

    for cell in cells:
        x, y = points[cell]
        ranked: list[tuple[float, int]] = []
        for region_id in region_ids:
            sx, sy = seed_points[region_id]
            distance2 = (x - sx) ** 2 + (y - sy) ** 2
            size_bias = (targets[region_id] / max(mean_target, 1.0)) ** 0.22
            noise = 0.96 + _hash_unit(f"{seed}:voronoi:{region_id}:{cell}") * 0.08
            score = distance2 / max(size_bias, 0.01) * noise
            ranked.append((score, region_id))
        ranked.sort(key=lambda item: (item[0], item[1]))
        preferences[cell] = ranked
        first_score, first_region = ranked[0]
        heapq.heappush(heap, (first_score, serial, cell, 0, first_region))
        serial += 1

    while heap and len(assignments) < len(cells):
        _, _, cell, rank, region_id = heapq.heappop(heap)
        if cell in assignments:
            continue
        if remaining.get(region_id, 0) > 0:
            assignments[cell] = region_id
            remaining[region_id] -= 1
            continue

        next_rank = rank + 1
        ranked = preferences[cell]
        if next_rank < len(ranked):
            next_score, next_region = ranked[next_rank]
            heapq.heappush(heap, (next_score, serial, cell, next_rank, next_region))
            serial += 1

    if len(assignments) < len(cells):
        open_regions = [region_id for region_id, count in remaining.items() if count > 0]
        for cell in cells:
            if cell in assignments:
                continue
            if not open_regions:
                open_regions = region_ids
            score_by_region = {region_id: score for score, region_id in preferences[cell]}
            assignments[cell] = min(open_regions, key=lambda region_id: score_by_region[region_id])
            remaining[assignments[cell]] = remaining.get(assignments[cell], 0) - 1
            open_regions = [region_id for region_id in open_regions if remaining.get(region_id, 0) > 0]

    return assignments


def _region_cell_targets(region_ids: list[int], weights: dict[int, int], cell_count: int) -> dict[int, int]:
    total_weight = sum(max(weights[region_id], 1) for region_id in region_ids)
    raw = {
        region_id: max(1.0, cell_count * max(weights[region_id], 1) / max(total_weight, 1))
        for region_id in region_ids
    }
    targets = {region_id: max(1, int(math.floor(raw[region_id]))) for region_id in region_ids}
    while sum(targets.values()) < cell_count:
        region_id = max(region_ids, key=lambda item: (raw[item] - targets[item], weights[item], -item))
        targets[region_id] += 1
    while sum(targets.values()) > cell_count:
        candidates = [region_id for region_id in region_ids if targets[region_id] > 1]
        if not candidates:
            break
        region_id = min(candidates, key=lambda item: (raw[item] - targets[item], weights[item], item))
        targets[region_id] -= 1
    return targets


def _attractor_points(free: list[int], points: list[list[float]], seed: str) -> list[tuple[float, float, float]]:
    xs = [points[cell][0] for cell in free]
    ys = [points[cell][1] for cell in free]
    width = max(max(xs) - min(xs), 1.0)
    height = max(max(ys) - min(ys), 1.0)
    radius = max(width, height) * 0.42
    centers = sorted(free, key=lambda cell: -_hash_unit(f"{seed}:attractor:{cell}"))[:3]
    return [(points[cell][0], points[cell][1], radius * (0.72 + index * 0.22)) for index, cell in enumerate(centers)]


def _rank_percentiles(values: dict[str, float], ids: list[str]) -> dict[str, float]:
    if not ids:
        return {}
    ordered = sorted(ids, key=lambda item: (float(values.get(item, 0.0)), stable_int(item)))
    denominator = max(len(ordered), 1)
    return {disease_id: (rank + 1) / denominator for rank, disease_id in enumerate(ordered)}


def _burg_group(percentile: float) -> str:
    if percentile >= 0.9:
        return "city"
    if percentile >= 0.58:
        return "town"
    if percentile >= 0.18:
        return "village"
    return "hamlet"


def _scaled_metric(
    rows_by_id: dict[str, dict[str, Any]],
    disease_ids: list[str],
    metric: str | None,
    out_min: float,
    out_max: float,
    *,
    default: float,
) -> dict[str, float]:
    if not metric:
        return {disease_id: default for disease_id in disease_ids}
    raw = {disease_id: _float(rows_by_id[disease_id].get(metric), 0.0) for disease_id in disease_ids}
    values = [math.log1p(max(0.0, value)) for value in raw.values()]
    lo, hi = min(values), max(values)
    if hi == lo:
        return {disease_id: (out_min + out_max) / 2 for disease_id in disease_ids}
    return {
        disease_id: out_min + (math.log1p(max(0.0, raw[disease_id])) - lo) / (hi - lo) * (out_max - out_min)
        for disease_id in disease_ids
    }


def _scaled_present_metric(
    rows_by_id: dict[str, dict[str, Any]],
    disease_ids: list[str],
    metric: str | None,
    out_min: float,
    out_max: float,
    *,
    missing: float,
    default: float | None = None,
) -> dict[str, float]:
    if not metric:
        value = missing if default is None else default
        return {disease_id: value for disease_id in disease_ids}

    raw = {
        disease_id: _float(rows_by_id[disease_id].get(metric), 0.0)
        for disease_id in disease_ids
        if rows_by_id[disease_id].get(metric) is not None and _float(rows_by_id[disease_id].get(metric), 0.0) > 0
    }
    if not raw:
        return {disease_id: missing for disease_id in disease_ids}

    values = [math.log1p(value) for value in raw.values()]
    lo, hi = min(values), max(values)
    scaled: dict[str, float] = {}
    for disease_id in disease_ids:
        if disease_id not in raw:
            scaled[disease_id] = missing
            continue
        if hi == lo:
            scaled[disease_id] = (out_min + out_max) / 2
            continue
        scaled[disease_id] = out_min + (math.log1p(raw[disease_id]) - lo) / (hi - lo) * (out_max - out_min)
    return scaled


def _phase_precipitation_metric(
    rows_by_id: dict[str, dict[str, Any]],
    disease_ids: list[str],
    stages_metric: str | None,
    drug_count_metric: str | None,
) -> tuple[dict[str, float], dict[str, int]]:
    phase_by_disease = {
        disease_id: _max_clinical_phase(rows_by_id[disease_id].get(stages_metric), rows_by_id[disease_id].get(drug_count_metric))
        for disease_id in disease_ids
    }
    return {disease_id: phase * 25 for disease_id, phase in phase_by_disease.items()}, phase_by_disease


def _max_clinical_phase(stages: Any, drug_count: Any) -> int:
    if drug_count is None or _float(drug_count, 0.0) <= 0:
        return 0
    return max((PHASE_RANKS.get(stage, 0) for stage in _stage_values(stages)), default=0)


def _stage_values(stages: Any) -> list[str]:
    if stages is None:
        return []
    if isinstance(stages, str):
        text = stages.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                except (SyntaxError, ValueError):
                    parsed = None
            if isinstance(parsed, list):
                return _stage_values(parsed)
        return [part.strip().upper() for part in text.replace("|", ",").split(",") if part.strip()]
    if isinstance(stages, (list, tuple, set)):
        return [str(stage).strip().upper() for stage in stages if str(stage).strip()]
    return [str(stages).strip().upper()] if str(stages).strip() else []


def _phase_precipitation_glyphs(
    disease_ids: list[str],
    rows_by_id: dict[str, dict[str, Any]],
    disease_names: dict[str, str],
    burgs: list[Any],
    burg_id_by_disease: dict[str, int],
    phase_by_disease: dict[str, int],
    temperature_metric: str | None,
    drug_count_metric: str | None,
    stages_metric: str | None,
) -> list[dict[str, Any]]:
    glyphs: list[dict[str, Any]] = []
    for disease_id in disease_ids:
        row = rows_by_id[disease_id]
        burg = burgs[burg_id_by_disease[disease_id]]
        drug_count = _float(row.get(drug_count_metric), 0.0) if drug_count_metric else 0.0
        phase = int(phase_by_disease.get(disease_id, 0))
        radius = min(5.2, 3.0 + math.log1p(max(0.0, drug_count)) * 0.75 + phase * 0.08)
        title_lines = [f"{disease_names.get(disease_id, disease_id)} ({disease_id})"]
        if temperature_metric:
            title_lines.append(f"{temperature_metric}: {row.get(temperature_metric, 'missing')}")
        if drug_count_metric:
            title_lines.append(f"{drug_count_metric}: {row.get(drug_count_metric, 'missing')}")
        title_lines.append(f"maxPhase: {phase}")
        if stages_metric:
            stages = ", ".join(_stage_values(row.get(stages_metric))) or "none"
            title_lines.append(f"{stages_metric}: {stages}")
        glyphs.append(
            {
                "x": burg["x"],
                "y": burg["y"],
                "r": round(radius, 2),
                "phase": phase,
                "title": "\n".join(title_lines),
            }
        )
    return glyphs


def _biome_metric(rows_by_id: dict[str, dict[str, Any]], disease_ids: list[str], metric: str | None) -> dict[str, int]:
    if not metric:
        return {disease_id: 6 for disease_id in disease_ids}
    scaled = _scaled_metric(rows_by_id, disease_ids, metric, 0, 1, default=0.5)
    biomes = [3, 4, 5, 6, 7, 8, 9, 10, 12]
    return {disease_id: biomes[min(len(biomes) - 1, int(scaled[disease_id] * len(biomes)))] for disease_id in disease_ids}


def _categorical_layer(
    rows_by_id: dict[str, dict[str, Any]], disease_ids: list[str], metric: str | None, zero_name: str
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if not metric:
        return {disease_id: 0 for disease_id in disease_ids}, [{"name": zero_name, "i": 0, "origins": None}]
    categories = sorted({_clean_id(rows_by_id[d].get(metric)) for d in disease_ids if _clean_id(rows_by_id[d].get(metric))})
    category_id = {category: i + 1 for i, category in enumerate(categories)}
    religions = [{"name": zero_name, "i": 0, "origins": None}]
    for category, i in category_id.items():
        religions.append(
            {
                "i": i,
                "name": category,
                "type": "Organized",
                "form": "Evidence",
                "deity": None,
                "color": color_for_id(category),
                "code": category[:3].upper(),
                "origins": [0],
                "center": 0,
                "culture": 1,
                "expansionism": 1,
                "expansion": "global",
                "area": 0,
                "cells": 0,
                "rural": 0,
                "urban": 0,
                "lock": True,
            }
        )
    return {d: category_id.get(_clean_id(rows_by_id[d].get(metric)), 0) for d in disease_ids}, religions


def _goods_layer(rows_by_id: dict[str, dict[str, Any]], disease_ids: list[str], metric: str | None) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if not metric:
        return {disease_id: 0 for disease_id in disease_ids}, []
    categories = sorted({_clean_id(rows_by_id[d].get(metric)) for d in disease_ids if _clean_id(rows_by_id[d].get(metric))})
    category_id = {category: i + 1 for i, category in enumerate(categories)}
    goods = []
    for category, i in category_id.items():
        goods.append(
            {
                "i": i,
                "name": category,
                "tags": ["open-targets"],
                "icon": "good-custom",
                "color": color_for_id(category),
                "value": 1,
                "chance": 0,
                "unit": "score",
            }
        )
    return {d: category_id.get(_clean_id(rows_by_id[d].get(metric)), 0) for d in disease_ids}, goods


def _province_average(groups: dict[int, list[str]], values: dict[str, float], *, default: float) -> dict[int, float]:
    result: dict[int, float] = {}
    for key, disease_ids in groups.items():
        current = [values[d] for d in disease_ids if d in values]
        result[key] = sum(current) / len(current) if current else default
    return result


def _province_mode(groups: dict[int, list[str]], values: dict[str, int], *, default: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for key, disease_ids in groups.items():
        counts: dict[int, int] = defaultdict(int)
        for disease_id in disease_ids:
            counts[values.get(disease_id, default)] += 1
        result[key] = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0] if counts else default
    return result


def _summarize_regions(
    cell_region: list[int], cell_pop: list[float], cell_burg: list[int], burgs: list[Any], cell_area: float
) -> dict[int, dict[str, float]]:
    stats: dict[int, dict[str, float]] = defaultdict(lambda: {"cells": 0, "area": 0, "rural": 0, "urban": 0, "burgs": 0})
    for cell, region_id in enumerate(cell_region):
        if not region_id:
            continue
        stats[region_id]["cells"] += 1
        stats[region_id]["area"] += cell_area
        burg_id = cell_burg[cell]
        if burg_id:
            stats[region_id]["burgs"] += 1
            stats[region_id]["urban"] += float(burgs[burg_id].get("population", 0))
        else:
            stats[region_id]["rural"] += cell_pop[cell]
    return stats


def _build_routes(
    rows: Iterable[dict[str, Any]],
    source_col: str,
    target_col: str,
    weight_col: str,
    burg_id_by_disease: dict[str, int],
    burgs: list[Any],
    *,
    max_routes: int,
    min_weight: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    if max_routes <= 0:
        return [], {}

    candidates: dict[tuple[str, str], float] = {}
    for row in rows:
        source = _clean_id(row.get(source_col))
        target = _clean_id(row.get(target_col))
        if source == target or source not in burg_id_by_disease or target not in burg_id_by_disease:
            continue
        weight = _float(row.get(weight_col), 0.0)
        if weight < min_weight:
            continue
        pair = tuple(sorted((source, target)))
        if weight > candidates.get(pair, -math.inf):
            candidates[pair] = weight
        if len(candidates) > max_routes * 2:
            candidates = dict(
                sorted(candidates.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:max_routes]
            )

    sortable = sorted(
        ((-weight, source, target) for (source, target), weight in candidates.items())
    )[:max_routes]

    routes: list[dict[str, Any]] = []
    cell_routes: dict[str, dict[str, int]] = {}
    for negative_weight, source, target in sortable:
        weight = -negative_weight
        source_burg = burgs[burg_id_by_disease[source]]
        target_burg = burgs[burg_id_by_disease[target]]
        route_id = len(routes)
        points = [
            [source_burg["x"], source_burg["y"], source_burg["cell"]],
            [target_burg["x"], target_burg["y"], target_burg["cell"]],
        ]
        length = math.dist(points[0][:2], points[1][:2])
        routes.append(
            {
                "i": route_id,
                "group": "roads",
                "feature": 1,
                "points": points,
                "length": round(length, 2),
                "lock": True,
                "sourceDiseaseId": source,
                "targetDiseaseId": target,
                "colocalisationCount": int(weight) if weight.is_integer() else weight,
            }
        )
        cell_routes.setdefault(str(source_burg["cell"]), {})[str(target_burg["cell"])] = route_id
        cell_routes.setdefault(str(target_burg["cell"]), {})[str(source_burg["cell"])] = route_id
    return routes, cell_routes


def _build_notes(
    config: dict[str, Any],
    disease_ids: list[str],
    assignments: dict[str, Assignment],
    disease_names: dict[str, str],
    rows_by_id: dict[str, dict[str, Any]],
    burg_id_by_disease: dict[str, int],
) -> list[dict[str, Any]]:
    if not config.get("notes", {}).get("include_burg_notes", True):
        return []
    notes: list[dict[str, Any]] = []
    metric_columns = [value for value in config.get("layers", {}).values() if isinstance(value, str)]
    for disease_id in disease_ids:
        assignment = assignments[disease_id]
        row = rows_by_id[disease_id]
        metric_lines = [f"{column}: {row.get(column)}" for column in metric_columns if column in row and row.get(column) is not None]
        legend = [
            f"Open Targets disease id: {disease_id}",
            f"Primary ontology path: {' > '.join(assignment.path)}",
        ]
        if assignment.extra_parents:
            legend.append(f"Additional parents: {', '.join(assignment.extra_parents)}")
        legend.extend(metric_lines)
        notes.append({"id": f"burg{burg_id_by_disease[disease_id]}", "name": disease_names.get(disease_id, disease_id), "legend": "\n".join(legend)})
    return notes


def _write_manifest(
    path: Path,
    disease_ids: list[str],
    assignments: dict[str, Assignment],
    disease_names: dict[str, str],
    state_id_by_key: dict[str, int],
    province_id_by_key: dict[str, int],
    burg_id_by_disease: dict[str, int],
    routes: list[dict[str, Any]],
    states: list[dict[str, Any]],
    provinces: list[Any],
) -> None:
    state_key_by_id = {v: k for k, v in state_id_by_key.items()}
    province_key_by_id = {v: k for k, v in province_id_by_key.items()}
    manifest = {
        "states": {
            str(state["i"]): {"source_id": state_key_by_id[state["i"]], "name": state["name"]}
            for state in states[1:]
        },
        "provinces": {
            str(province["i"]): {
                "source_id": province_key_by_id[province["i"]],
                "name": province["name"],
                "state": province["state"],
            }
            for province in provinces[1:]
            if isinstance(province, dict)
        },
        "diseases": {
            disease_id: {
                "name": disease_names.get(disease_id, disease_id),
                "burg": burg_id_by_disease[disease_id],
                "state": state_id_by_key[assignments[disease_id].state_id],
                "province": province_id_by_key[assignments[disease_id].province_id],
                "primary_path": list(assignments[disease_id].path),
                "primary_path_names": [disease_names.get(node, node) for node in assignments[disease_id].path],
                "extra_parents": list(assignments[disease_id].extra_parents),
                "extra_parent_names": [disease_names.get(node, node) for node in assignments[disease_id].extra_parents],
            }
            for disease_id in disease_ids
        },
        "routes": {
            str(route["i"]): {
                "source_disease_id": route.get("sourceDiseaseId"),
                "target_disease_id": route.get("targetDiseaseId"),
                "colocalisation_count": route.get("colocalisationCount"),
                "points": route["points"],
                "length": route.get("length"),
            }
            for route in routes
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _neutral_state(state_count: int) -> dict[str, Any]:
    return {
        "i": 0,
        "name": "Neutrals",
        "form": "Anarchy",
        "formName": "",
        "fullName": "Neutrals",
        "color": "#cccccc",
        "center": 0,
        "pole": [0, 0],
        "culture": 0,
        "type": "Generic",
        "expansionism": 0,
        "area": 0,
        "burgs": 0,
        "cells": 0,
        "rural": 0,
        "urban": 0,
        "neighbors": [],
        "provinces": [],
        "diplomacy": ["x"] * (state_count + 1),
        "campaigns": [],
        "alert": 0,
        "military": [],
        "coa": {},
        "salesTax": 0,
        "pollTax": 0,
        "treasury": 0,
    }


def _hash_unit(value: str) -> float:
    return stable_int(value, 10**9) / 10**9


def _float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_name(value: Any, default: str) -> str:
    text = _clean_id(value)
    return text if text else default
