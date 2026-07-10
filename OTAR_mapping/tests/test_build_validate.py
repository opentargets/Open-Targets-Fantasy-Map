import csv
import colorsys
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from ot_fmg.azgaar import related_color_for_id, validate_map
from ot_fmg.config import load_config
from ot_fmg.converter import _generate_grid, build_map


class BuildValidateTests(unittest.TestCase):
    def test_builds_structurally_valid_map_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(
                root / "diseases.csv",
                ["disease_id", "disease_name"],
                [
                    ["D1", "Disease One"],
                    ["D2", "Disease Two"],
                    ["D3", "Disease Three"],
                    ["D4", "Disease Four"],
                ],
            )
            _write_csv(
                root / "edges.csv",
                ["child_id", "parent_id"],
                [
                    ["A", "ROOT"],
                    ["B", "ROOT"],
                    ["A1", "A"],
                    ["A2", "A"],
                    ["B1", "B"],
                    ["D1", "A1"],
                    ["D2", "A2"],
                    ["D3", "B1"],
                    ["D4", "A1"],
                    ["D4", "B1"],
                ],
            )
            _write_csv(
                root / "metrics.csv",
                ["disease_id", "target_count", "credible_set_count", "gwas_study_count", "evidence_count", "evidence_type"],
                [
                    ["D1", "10", "2", "5", "100", "genetic"],
                    ["D2", "20", "3", "8", "200", "known_drug"],
                    ["D3", "5", "9", "2", "150", "genetic"],
                    ["D4", "30", "1", "12", "300", "literature"],
                ],
            )
            _write_csv(
                root / "links.csv",
                ["source_id", "target_id", "score"],
                [["D1", "D4", "0.9"], ["D2", "D3", "0.7"], ["D1", "missing", "1.0"]],
            )
            config_path = root / "config.yml"
            config_path.write_text(
                """
inputs:
  diseases:
    path: diseases.csv
    id: disease_id
    name: disease_name
  ontology:
    path: edges.csv
    child: child_id
    parent: parent_id
  metrics:
    path: metrics.csv
    disease_id: disease_id
  links:
    path: links.csv
    source: source_id
    target: target_id
    weight: score
ontology:
  root_ids: [ROOT]
  skip_roots: true
map:
  name: Test Atlas
  width: 800
  height: 500
  cells: 1200
  max_routes: 10
layers:
  elevation: target_count
  precipitation: credible_set_count
  biome: gwas_study_count
  population: evidence_count
  religion: evidence_type
""",
                encoding="utf-8",
            )
            config = load_config(config_path)
            out_path = root / "test.map"
            result = build_map(config, out_path)

            self.assertEqual(result.disease_count, 4)
            self.assertEqual(result.route_count, 2)
            self.assertTrue(result.manifest_path.exists())
            self.assertEqual(validate_map(out_path), [])

            sections = out_path.read_bytes().decode("utf-8").split("\r\n")
            self.assertEqual(len(sections), 46)
            self.assertIn("<svg", sections[5])
            self.assertIn('shape-rendering="optimizeSpeed"', sections[5])
            self.assertIn('<g id="cells"', sections[5])
            self.assertNotIn("<path", sections[5].split('<g id="cells"', 1)[1].split("</g>", 1)[0])
            self.assertNotIn('filter="blur(6px)"', sections[5].split('<g id="statesHalo"', 1)[1].split("</g>", 1)[0])
            icons_svg = sections[5].split('<g id="icons"', 1)[1].split('<g id="labels"', 1)[0]
            self.assertNotIn('class="hidden"', icons_svg)
            self.assertNotIn("<title>", icons_svg)

    def test_can_opt_into_serialized_cell_svg_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "diseases.csv", ["disease_id", "disease_name"], [["D1", "Disease One"], ["D2", "Disease Two"]])
            _write_csv(
                root / "edges.csv",
                ["child_id", "parent_id"],
                [["A", "ROOT"], ["A1", "A"], ["D1", "A1"], ["D2", "A1"]],
            )
            config_path = root / "config.yml"
            config_path.write_text(
                """
inputs:
  diseases:
    path: diseases.csv
    id: disease_id
    name: disease_name
  ontology:
    path: edges.csv
    child: child_id
    parent: parent_id
ontology:
  root_ids: [ROOT]
map:
  width: 500
  height: 300
  cells: 200
svg:
  cells_layer: true
""",
                encoding="utf-8",
            )

            out_path = root / "cells.map"
            build_map(load_config(config_path), out_path)

            sections = out_path.read_bytes().decode("utf-8").split("\r\n")
            self.assertIn("<path", sections[5].split('<g id="cells"', 1)[1].split("</g>", 1)[0])

    def test_builds_from_flat_states_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_rows = [
                {
                    "provinceId": "P1",
                    "therapeuticArea": "TA1",
                    "therapeuticAreaName": "Area One",
                    "provinceName": "Province One",
                    "leafId": "D1",
                    "leafName": "Disease One",
                    "populationSize": 2,
                },
                {
                    "provinceId": "P2",
                    "therapeuticArea": "TA1",
                    "therapeuticAreaName": "Area One",
                    "provinceName": "Province Two",
                    "leafId": "D2",
                    "leafName": "Disease Two",
                    "populationSize": 4,
                },
                {
                    "provinceId": "P3",
                    "therapeuticArea": "TA2",
                    "therapeuticAreaName": "Area Two",
                    "provinceName": "Province Three",
                    "leafId": "D2",
                    "leafName": "Disease Two",
                    "populationSize": 5,
                },
                {
                    "provinceId": "P3",
                    "therapeuticArea": "TA2",
                    "therapeuticAreaName": "Area Two",
                    "provinceName": "Province Three",
                    "leafId": "D3",
                    "leafName": "Disease Three",
                    "populationSize": 1,
                },
            ]
            state_path = root / "states.json"
            state_path.write_text("\n".join(json.dumps(row) for row in state_rows), encoding="utf-8")
            config = {
                "_config_dir": str(root),
                "inputs": {"state_rows": {"path": "states.json"}},
                "ontology": {"skip_roots": True, "root_ids": []},
                "map": {"name": "State Rows Test", "width": 600, "height": 400, "cells": 800, "max_routes": 0},
                "layers": {},
                "notes": {"include_burg_notes": False},
                "svg": {"max_burg_icons": 100},
            }
            out_path = root / "states.map"
            result = build_map(config, out_path)

            self.assertEqual(result.disease_count, 3)
            self.assertEqual(result.state_count, 2)
            self.assertEqual(validate_map(out_path), [])

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["states"]["1"]["name"], "Area One")
            self.assertIn("P2", manifest["diseases"]["D2"]["extra_parents"])

            sections = out_path.read_bytes().decode("utf-8").split("\r\n")
            grid = json.loads(sections[6])
            states = json.loads(sections[14])
            provinces = json.loads(sections[30])
            cell_states = _int_csv(sections[25])
            cell_provinces = _int_csv(sections[27])
            cell_by_point = {tuple(point): cell for cell, point in enumerate(grid["points"])}
            for state in states[1:]:
                pole_cell = cell_by_point[tuple(state["pole"])]
                self.assertEqual(cell_states[pole_cell], state["i"])
            for province in provinces[1:]:
                state = states[province["state"]]
                state_hue = _hex_hue(state["color"])
                province_hue = _hex_hue(province["color"])
                self.assertLessEqual(_hue_distance(state_hue, province_hue), 0.06)
                pole_cell = cell_by_point[tuple(province["pole"])]
                self.assertEqual(cell_provinces[pole_cell], province["i"])

    def test_builds_open_targets_feature_layers_from_gz_state_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_rows = [
                {
                    "provinceId": "P1",
                    "therapeuticArea": "TA1",
                    "therapeuticAreaName": "Area One",
                    "provinceName": "Province One",
                    "leafId": "D1",
                    "leafName": "Disease One",
                    "populationSize": 2,
                    "targetCount": 9,
                    "drugCount": 2,
                    "maxClinicalStages": ["PHASE_2", "UNKNOWN"],
                },
                {
                    "provinceId": "P1",
                    "therapeuticArea": "TA1",
                    "therapeuticAreaName": "Area One",
                    "provinceName": "Province One",
                    "leafId": "D2",
                    "leafName": "Disease Two",
                    "populationSize": 1,
                },
                {
                    "provinceId": "P2",
                    "therapeuticArea": "TA2",
                    "therapeuticAreaName": "Area Two",
                    "provinceName": "Province Two",
                    "leafId": "D3",
                    "leafName": "Disease Three",
                    "populationSize": 4,
                    "targetCount": 27,
                    "drugCount": 4,
                    "maxClinicalStages": ["APPROVAL", "PHASE_3"],
                },
            ]
            state_path = root / "states.json.gz"
            with gzip.open(state_path, "wt", encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(row) for row in state_rows))

            config = {
                "_config_dir": str(root),
                "inputs": {
                    "state_rows": {"path": "states.json.gz"},
                    "metrics": {"path": "states.json.gz", "disease_id": "leafId"},
                },
                "ontology": {"skip_roots": True, "root_ids": []},
                "map": {"name": "Feature Rows Test", "width": 600, "height": 400, "cells": 800, "max_routes": 0},
                "layers": {
                    "elevation": "drugCount",
                    "precipitation": "maxClinicalStages",
                    "temperature": "targetCount",
                    "phase_drug_count": "drugCount",
                    "population": "populationSizeTotal",
                },
                "notes": {"include_burg_notes": False},
                "svg": {"max_burg_icons": 100},
            }
            out_path = root / "feature-states.map"
            build_map(config, out_path)

            self.assertEqual(validate_map(out_path), [])
            sections = out_path.read_bytes().decode("utf-8").split("\r\n")
            self.assertNotIn("phasePrecipitation", sections[5])
            self.assertIn('<g id="prec"/>', sections[5])
            self.assertIn('data-size="34" font-size="34"', sections[5])
            self.assertIn('<g id="landHeights" opacity="1" scheme="light"', sections[5])
            self.assertIn('<g id="oceanHeights" data-render="0" opacity="1" scheme="light"', sections[5])

            manifest = json.loads(out_path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
            burgs = json.loads(sections[15])
            grid_h = _int_csv(sections[7])
            grid_prec = _int_csv(sections[8])
            grid_temp = _int_csv(sections[11])
            cell_burg = _int_csv(sections[17])

            d1_cell = burgs[manifest["diseases"]["D1"]["burg"]]["cell"]
            d2_cell = burgs[manifest["diseases"]["D2"]["burg"]]["cell"]
            d3_cell = burgs[manifest["diseases"]["D3"]["burg"]]["cell"]

            self.assertEqual(grid_temp[d1_cell], 2)
            self.assertEqual(grid_temp[d2_cell], 0)
            self.assertEqual(grid_temp[d3_cell], 42)
            self.assertEqual(grid_h[d1_cell], 35)
            self.assertEqual(grid_h[d2_cell], 24)
            self.assertEqual(grid_h[d3_cell], 90)
            self.assertEqual(grid_prec[d1_cell], 50)
            self.assertEqual(grid_prec[d2_cell], 0)
            self.assertEqual(grid_prec[d3_cell], 100)
            self.assertTrue(all(grid_temp[i] == 0 for i, burg_id in enumerate(cell_burg) if not burg_id))

    def test_streams_partitioned_colocalisations_with_threshold_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_rows = [
                {
                    "provinceId": "P1",
                    "therapeuticArea": "TA1",
                    "therapeuticAreaName": "Area One",
                    "provinceName": "Province One",
                    "leafId": disease_id,
                    "leafName": disease_id,
                    "populationSize": 1,
                }
                for disease_id in ("D1", "D2", "D3")
            ]
            state_path = root / "states.json.gz"
            with gzip.open(state_path, "wt", encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(row) for row in state_rows))

            links_path = root / "colocalisations"
            links_path.mkdir()
            link_parts = [
                [
                    {"leftDiseaseId": "D1", "rightDiseaseId": "D2", "colocalisationCount": 24},
                    {"leftDiseaseId": "D1", "rightDiseaseId": "D3", "colocalisationCount": 30},
                ],
                [
                    {"leftDiseaseId": "D3", "rightDiseaseId": "D1", "colocalisationCount": 35},
                    {"leftDiseaseId": "D2", "rightDiseaseId": "D3", "colocalisationCount": 25},
                    {"leftDiseaseId": "D1", "rightDiseaseId": "missing", "colocalisationCount": 100},
                ],
            ]
            for index, rows in enumerate(link_parts):
                with gzip.open(links_path / f"part-{index:05d}.json.gz", "wt", encoding="utf-8") as handle:
                    handle.write("\n".join(json.dumps(row) for row in rows))

            config = {
                "_config_dir": str(root),
                "inputs": {
                    "state_rows": {"path": "states.json.gz"},
                    "links": {
                        "path": "colocalisations",
                        "source": "leftDiseaseId",
                        "target": "rightDiseaseId",
                        "weight": "colocalisationCount",
                        "min_weight": 25,
                    },
                },
                "ontology": {"skip_roots": True, "root_ids": []},
                "map": {"name": "Coloc Test", "width": 600, "height": 400, "cells": 800, "max_routes": 2},
                "layers": {},
                "notes": {"include_burg_notes": False},
                "svg": {"max_burg_icons": 100},
            }
            out_path = root / "coloc.map"
            result = build_map(config, out_path)

            self.assertEqual(result.route_count, 2)
            self.assertEqual(validate_map(out_path), [])
            sections = out_path.read_bytes().decode("utf-8").split("\r\n")
            routes = json.loads(sections[37])
            self.assertEqual([route["colocalisationCount"] for route in routes], [35, 25])
            self.assertEqual(routes[0]["sourceDiseaseId"], "D1")
            self.assertEqual(routes[0]["targetDiseaseId"], "D3")
            roads_svg = sections[5].split('<g id="roads"', 1)[1].split("</g>", 1)[0]
            self.assertIn('<path id="route0"', roads_svg)
            self.assertIn('<path id="route1"', roads_svg)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["routes"]["0"]["colocalisation_count"], 35)
            self.assertEqual(manifest["routes"]["1"]["source_disease_id"], "D2")

    def test_related_color_keeps_provinces_in_state_hue_family(self):
        state_color = "#7aa6d8"
        province_colors = [
            related_color_for_id(state_color, f"P{i}", index=i, count=8)
            for i in range(8)
        ]
        state_hue = _hex_hue(state_color)

        self.assertGreater(len(set(province_colors)), 1)
        for province_color in province_colors:
            self.assertLessEqual(_hue_distance(state_hue, _hex_hue(province_color)), 0.06)

    def test_grid_generation_preserves_map_aspect_for_small_subsets(self):
        grid = _generate_grid(2600, 1600, 2848, 100000)

        self.assertGreater(grid["cellsX"], 1)
        self.assertGreater(grid["cellsY"], 1)
        self.assertAlmostEqual(grid["cellsX"] / grid["cellsY"], 2600 / 1600, delta=0.2)
        self.assertEqual(grid["cellsDesired"], 2848)
        self.assertGreaterEqual(len(grid["points"]), 2848)

    def test_grid_generation_uses_fmg_style_jittered_seed_points(self):
        grid = _generate_grid(2600, 1600, 4000, 100000)
        spacing = grid["spacing"]
        offsets = []
        for cell, (x, y) in enumerate(grid["points"]):
            col = cell % grid["cellsX"]
            row = cell // grid["cellsX"]
            center_x = spacing / 2 + col * spacing
            center_y = spacing / 2 + row * spacing
            offsets.append(((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 / spacing)

        self.assertGreater(sum(offsets) / len(offsets), 0.25)
        self.assertLess(max(offsets), 0.7)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _int_csv(value: str) -> list[int]:
    return [int(float(item)) for item in value.split(",") if item != ""]


def _hex_hue(value: str) -> float:
    r = int(value[1:3], 16) / 255
    g = int(value[3:5], 16) / 255
    b = int(value[5:7], 16) / 255
    return colorsys.rgb_to_hls(r, g, b)[0]


def _hue_distance(a: float, b: float) -> float:
    diff = abs(a - b)
    return min(diff, 1 - diff)


if __name__ == "__main__":
    unittest.main()
