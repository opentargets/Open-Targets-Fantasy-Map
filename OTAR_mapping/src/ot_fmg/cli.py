from __future__ import annotations

import argparse
from pathlib import Path

from .azgaar import validate_map
from .config import config_with_defaults, load_config
from .converter import build_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ot-fmg", description="Build Azgaar .map files from Open Targets-style tables")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build an Azgaar .map file")
    build_parser.add_argument("--config", required=True, help="YAML or JSON converter config")
    build_parser.add_argument("--out", required=True, help="Output .map file")
    build_parser.add_argument("--manifest", help="Optional output manifest JSON path")

    states_parser = subparsers.add_parser("build-states-json", help="Build directly from a flat Open Targets states JSON/JSONL file")
    states_parser.add_argument("--states-json", required=True, help="Path to newline-delimited states.json")
    states_parser.add_argument("--out", required=True, help="Output .map file")
    states_parser.add_argument("--manifest", help="Optional output manifest JSON path")
    states_parser.add_argument("--name", default="Open Targets Disease Atlas", help="Map name")
    states_parser.add_argument("--width", type=int, default=2600, help="Map width")
    states_parser.add_argument("--height", type=int, default=1600, help="Map height")
    states_parser.add_argument("--cells", type=int, help="Requested cell count")
    states_parser.add_argument("--cell-multiplier", type=float, help="Default cells per disease burg when --cells is omitted")
    states_parser.add_argument(
        "--colocalisations",
        help="JSON/JSONL/CSV file or partition directory containing disease colocalisation counts",
    )
    states_parser.add_argument(
        "--min-colocalisations",
        type=int,
        default=25000,
        help="Minimum colocalisationCount required for a road (default: 25000)",
    )
    states_parser.add_argument(
        "--max-routes",
        type=int,
        help="Maximum rendered disease-disease routes (default: 250 with --colocalisations, otherwise 0)",
    )
    states_parser.add_argument("--include-notes", action="store_true", help="Include one Azgaar note per disease burg")
    states_parser.add_argument("--max-burg-icons", type=int, default=5000, help="Maximum burg icons serialized into the SVG preview")
    states_parser.add_argument("--render-cells-layer", action="store_true", help="Serialize visible cell outline paths into the SVG preview")
    states_parser.add_argument(
        "--open-targets-features",
        action="store_true",
        help=(
            "Use Open Targets additional fields: targetCount as temperature, "
            "drugCount as elevation, and maxClinicalStages as phase-sized precipitation"
        ),
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a generated .map file")
    validate_parser.add_argument("map_file", help="Path to .map file")

    args = parser.parse_args(argv)
    if args.command == "build":
        config = load_config(args.config)
        result = build_map(config, Path(args.out), Path(args.manifest) if args.manifest else None)
        print(f"Wrote {result.map_path}")
        print(f"Wrote {result.manifest_path}")
        print(
            "Built "
            f"{result.disease_count} diseases, {result.province_count} provinces, "
            f"{result.state_count} states, {result.route_count} routes, {result.cell_count} cells"
        )
        return 0

    if args.command == "build-states-json":
        states_path = Path(args.states_json).expanduser()
        max_routes = args.max_routes if args.max_routes is not None else (250 if args.colocalisations else 0)
        loaded = {
            "inputs": {"state_rows": {"path": str(states_path)}},
            "map": {
                "name": args.name,
                "width": args.width,
                "height": args.height,
                "cells": args.cells,
                "cell_multiplier": args.cell_multiplier,
                "max_routes": max_routes,
            },
            "notes": {"include_burg_notes": args.include_notes},
            "svg": {"max_burg_icons": args.max_burg_icons, "cells_layer": args.render_cells_layer},
        }
        if args.colocalisations:
            loaded["inputs"]["links"] = {
                "path": str(Path(args.colocalisations).expanduser()),
                "source": "leftDiseaseId",
                "target": "rightDiseaseId",
                "weight": "colocalisationCount",
                "min_weight": args.min_colocalisations,
            }
        if args.open_targets_features:
            loaded["inputs"]["metrics"] = {"path": str(states_path), "disease_id": "leafId"}
            loaded["layers"] = {
                "elevation": "drugCount",
                "precipitation": "maxClinicalStages",
                "temperature": "targetCount",
                "phase_drug_count": "drugCount",
                "population": "populationSizeTotal",
            }
        config = config_with_defaults(loaded, states_path.parent)
        result = build_map(config, Path(args.out), Path(args.manifest) if args.manifest else None)
        print(f"Wrote {result.map_path}")
        print(f"Wrote {result.manifest_path}")
        print(
            "Built "
            f"{result.disease_count} diseases, {result.province_count} provinces, "
            f"{result.state_count} states, {result.route_count} routes, {result.cell_count} cells"
        )
        return 0

    if args.command == "validate":
        errors = validate_map(Path(args.map_file))
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(f"{args.map_file} is structurally valid")
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2
