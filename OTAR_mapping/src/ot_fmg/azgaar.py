from __future__ import annotations

import hashlib
import html
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


BIOME_COLORS = [
    "#466eab",
    "#fbe79f",
    "#b5b887",
    "#d2d082",
    "#c8d68f",
    "#b6d95d",
    "#29bc56",
    "#7dcb35",
    "#409c43",
    "#4b6b32",
    "#96784b",
    "#d5e7eb",
    "#0b9131",
]
BIOME_HABITABILITY = [0, 4, 10, 22, 30, 50, 100, 80, 90, 12, 4, 0, 12]
BIOME_NAMES = [
    "Marine",
    "Hot desert",
    "Cold desert",
    "Savanna",
    "Grassland",
    "Tropical seasonal forest",
    "Temperate deciduous forest",
    "Tropical rainforest",
    "Temperate rainforest",
    "Taiga",
    "Tundra",
    "Glacier",
    "Wetland",
]


@dataclass
class MapPayload:
    name: str
    version: str
    seed: int
    map_id: int
    width: int
    height: int
    grid_general: dict[str, Any]
    grid_h: list[int]
    grid_prec: list[int]
    grid_f: list[int]
    grid_t: list[int]
    grid_temp: list[int]
    features: list[Any]
    cultures: list[dict[str, Any]]
    states: list[dict[str, Any]]
    burgs: list[Any]
    cell_biome: list[int]
    cell_burg: list[int]
    cell_conf: list[int]
    cell_culture: list[int]
    cell_fl: list[int]
    cell_pop: list[float]
    cell_r: list[int]
    cell_s: list[int]
    cell_state: list[int]
    cell_religion: list[int]
    cell_province: list[int]
    religions: list[dict[str, Any]]
    provinces: list[Any]
    rivers: list[dict[str, Any]] = field(default_factory=list)
    markers: list[dict[str, Any]] = field(default_factory=list)
    cell_routes: dict[str, dict[str, int]] = field(default_factory=dict)
    routes: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    ice: list[dict[str, Any]] = field(default_factory=list)
    cell_good: list[int] = field(default_factory=list)
    goods: list[dict[str, Any]] = field(default_factory=list)
    markets: list[dict[str, Any]] = field(default_factory=list)
    deals: list[dict[str, Any]] = field(default_factory=list)
    cell_market: list[int] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    svg: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    style_preset: str = "ancient"


def write_map(payload: MapPayload, path: Path) -> None:
    sections = build_sections(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(sections), encoding="utf-8", newline="")


def build_sections(payload: MapPayload) -> list[str]:
    today = date.today()
    params = "|".join(
        [
            str(payload.version),
            "File can be loaded in azgaar.github.io/Fantasy-Map-Generator",
            f"{today.year}-{today.month}-{today.day}",
            str(payload.seed),
            str(payload.width),
            str(payload.height),
            str(payload.map_id),
        ]
    )

    options = {
        "pinNotes": False,
        "winds": [225, 45, 225, 315, 135, 315],
        "temperatureEquator": 21,
        "temperatureNorthPole": -16,
        "temperatureSouthPole": -15,
        "stateLabelsMode": "auto",
        "showBurgPreview": True,
        "burgs": {"groups": _burg_group_options()},
        "year": today.year,
        "era": "Common Era",
        "eraShort": "CE",
        **payload.options,
    }
    settings = [
        "km",
        "5",
        "square",
        "m",
        "2",
        "\u00b0C",
        "",
        "",
        "",
        "",
        "",
        "",
        "1000",
        "1",
        "25",
        "36",
        "",
        "",
        "100",
        _json(options),
        payload.name,
        "0",
        payload.style_preset,
        "1",
        "10",
        "50",
        "1.2",
    ]

    n = len(payload.cell_state)
    cell_good = payload.cell_good or [0] * n
    cell_market = payload.cell_market or [0] * n

    sections = [
        params,
        "|".join(settings),
        _json({"latT": 45, "latN": 41.4, "latS": -3.6, "lonT": 86.3, "lonW": -43.1, "lonE": 43.2}),
        "|".join([",".join(BIOME_COLORS), _csv(BIOME_HABITABILITY), ",".join(BIOME_NAMES)]),
        _json(payload.notes),
        payload.svg,
        _json(payload.grid_general),
        _csv(payload.grid_h),
        _csv(payload.grid_prec),
        _csv(payload.grid_f),
        _csv(payload.grid_t),
        _csv(payload.grid_temp),
        _json(payload.features),
        _json(payload.cultures),
        _json(payload.states),
        _json(payload.burgs),
        _csv(payload.cell_biome),
        _csv(payload.cell_burg),
        _csv(payload.cell_conf),
        _csv(payload.cell_culture),
        _csv(payload.cell_fl),
        _csv([round(value, 4) for value in payload.cell_pop]),
        _csv(payload.cell_r),
        "",
        _csv(payload.cell_s),
        _csv(payload.cell_state),
        _csv(payload.cell_religion),
        _csv(payload.cell_province),
        "",
        _json(payload.religions),
        _json(payload.provinces),
        "",
        _json(payload.rivers),
        "",
        "[]",
        _json(payload.markers),
        _json(payload.cell_routes),
        _json(payload.routes),
        _json(payload.zones),
        _json(payload.ice),
        _csv(cell_good),
        _json(payload.goods),
        _json(payload.markets),
        _json(payload.deals),
        _csv(cell_market),
        "",
    ]
    if len(sections) != 46:
        raise AssertionError(f"Expected 46 map sections, got {len(sections)}")
    return sections


def validate_map(path: Path) -> list[str]:
    raw = path.read_bytes().decode("utf-8")
    sections = raw.split("\r\n")
    errors: list[str] = []
    if len(sections) != 46:
        errors.append(f"Expected 46 CRLF-delimited sections, got {len(sections)}")
        return errors
    if not sections[5].lstrip().startswith("<svg"):
        errors.append("Section 5 must contain serialized SVG")

    def parse_json(index: int, label: str) -> Any:
        try:
            return json.loads(sections[index])
        except Exception as exc:
            errors.append(f"Section {index} ({label}) is invalid JSON: {exc}")
            return None

    grid = parse_json(6, "gridGeneral")
    features = parse_json(12, "pack.features")
    cultures = parse_json(13, "pack.cultures")
    states = parse_json(14, "pack.states")
    burgs = parse_json(15, "pack.burgs")
    religions = parse_json(29, "pack.religions")
    provinces = parse_json(30, "pack.provinces")
    routes = parse_json(37, "pack.routes")

    if not isinstance(grid, dict):
        return errors
    points = grid.get("points") or []
    n = len(points)
    for index, label in [
        (7, "grid.cells.h"),
        (8, "grid.cells.prec"),
        (9, "grid.cells.f"),
        (10, "grid.cells.t"),
        (11, "grid.cells.temp"),
    ]:
        if _count_csv(sections[index]) != n:
            errors.append(f"Section {index} ({label}) length does not match grid points ({n})")

    pack_length_sections = {
        16: "pack.cells.biome",
        17: "pack.cells.burg",
        18: "pack.cells.conf",
        19: "pack.cells.culture",
        20: "pack.cells.fl",
        21: "pack.cells.pop",
        22: "pack.cells.r",
        24: "pack.cells.s",
        25: "pack.cells.state",
        26: "pack.cells.religion",
        27: "pack.cells.province",
        40: "pack.cells.good",
        44: "pack.cells.market",
    }
    for index, label in pack_length_sections.items():
        if _count_csv(sections[index]) != n:
            errors.append(f"Section {index} ({label}) length does not match pack cell count ({n})")

    cell_burg = _ints(sections[17])
    cell_state = _ints(sections[25])
    cell_province = _ints(sections[27])

    if isinstance(states, list):
        for state_id in sorted(set(cell_state)):
            if state_id and (state_id >= len(states) or not isinstance(states[state_id], dict)):
                errors.append(f"Cell references missing state id {state_id}")
    if isinstance(provinces, list):
        for province_id in sorted(set(cell_province)):
            if province_id and (province_id >= len(provinces) or not isinstance(provinces[province_id], dict)):
                errors.append(f"Cell references missing province id {province_id}")
    if isinstance(burgs, list):
        seen_cells: set[int] = set()
        for burg in burgs[1:]:
            if not isinstance(burg, dict) or burg.get("removed"):
                continue
            cell = burg.get("cell")
            burg_id = burg.get("i")
            if not isinstance(cell, int) or cell < 0 or cell >= n:
                errors.append(f"Burg {burg_id} has invalid cell {cell}")
                continue
            if cell in seen_cells:
                errors.append(f"Multiple burgs occupy cell {cell}")
            seen_cells.add(cell)
            if burg_id and (burg_id >= 65536):
                errors.append(f"Burg id {burg_id} exceeds Uint16Array capacity")
            if burg_id and cell_burg[cell] != burg_id:
                errors.append(f"Burg {burg_id} is not mirrored in pack.cells.burg[{cell}]")
            if not burg.get("name"):
                errors.append(f"Burg {burg_id} has no name")
    if isinstance(provinces, list) and isinstance(states, list):
        for province in provinces[1:]:
            if not isinstance(province, dict):
                continue
            state_id = province.get("state")
            if not isinstance(state_id, int) or state_id <= 0 or state_id >= len(states):
                errors.append(f"Province {province.get('i')} has invalid state {state_id}")
    if isinstance(routes, list):
        for route in routes:
            points_for_route = route.get("points") if isinstance(route, dict) else None
            if not points_for_route or len(points_for_route) < 2:
                errors.append(f"Route {route.get('i') if isinstance(route, dict) else '?'} has fewer than two points")

    for label, value in [("features", features), ("cultures", cultures), ("religions", religions)]:
        if not isinstance(value, list):
            errors.append(f"{label} is not a list")

    return errors


def build_svg(
    width: int,
    height: int,
    states: list[dict[str, Any]],
    provinces: list[Any],
    burgs: list[Any],
    routes: list[dict[str, Any]],
    state_rects: dict[int, tuple[float, float, float, float]],
    province_rects: dict[int, tuple[float, float, float, float]],
    grid: dict[str, Any],
    cell_state: list[int],
    cell_province: list[int],
    *,
    max_burg_icons: int,
    shape_rendering: str = "optimizeSpeed",
    render_state_fill: bool = False,
    render_state_halo: bool = False,
    render_province_labels: bool = False,
    render_cells_layer: bool = False,
    clip_to_land: bool = False,
    precipitation_glyphs: list[dict[str, Any]] | None = None,
) -> str:
    land_path = _blob_path(width * 0.5, height * 0.5, width * 0.515, height * 0.505, "landmass", 120, 0.045)
    ocean_ring_1 = _blob_path(width * 0.5, height * 0.5, width * 0.545, height * 0.535, "ocean-ring-1", 126, 0.04)
    ocean_ring_2 = _blob_path(width * 0.5, height * 0.5, width * 0.585, height * 0.575, "ocean-ring-2", 126, 0.035)
    ocean_ring_3 = _blob_path(width * 0.5, height * 0.5, width * 0.635, height * 0.625, "ocean-ring-3", 126, 0.03)
    state_paths = _region_fill_paths(cell_state, grid)
    state_border_path = _cell_border_path(cell_state, grid, "state")
    province_border_path = _cell_border_path(cell_province, grid, "province", same_state=cell_state)
    cell_layer_paths = _cell_layer_paths(width, height, grid)
    precipitation_layer = (
        _phase_precipitation_layer(precipitation_glyphs) if precipitation_glyphs else '    <g id="prec"/>'
    )
    state_clip_paths = []
    if render_state_fill and render_state_halo:
        for state in states[1:]:
            if not isinstance(state, dict):
                continue
            state_id = state["i"]
            if state_id in state_paths:
                state_clip_paths.append(f'<clipPath id="state-clip{state_id}"><use href="#state{state_id}"/></clipPath>')

    clip_attr = ' clip-path="url(#landClip)"' if clip_to_land else ""
    lines = [
        f'<svg id="map" width="{width}" height="{height}" viewBox="0 0 {width} {height}" version="1.1" xmlns="http://www.w3.org/2000/svg" style="background-color:#c9d4c3">',
        "  <defs>",
        '    <g id="filters">',
        '      <filter id="paper" x="-5%" y="-5%" width="110%" height="110%">',
        '        <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="4" seed="7" result="noise"/>',
        '        <feColorMatrix in="noise" type="saturate" values="0"/>',
        '        <feComponentTransfer><feFuncA type="table" tableValues="0 0.11"/></feComponentTransfer>',
        '        <feComposite in2="SourceGraphic" operator="over"/>',
        "      </filter>",
        '      <filter id="filter-sepia">',
        '        <feColorMatrix type="matrix" values="0.72 0.22 0.06 0 0.04 0.18 0.78 0.04 0 0.03 0.14 0.18 0.68 0 0.02 0 0 0 1 0"/>',
        "      </filter>",
        '      <filter id="dropShadow05" x="-20%" y="-20%" width="140%" height="140%">',
        '        <feDropShadow dx="1" dy="1" stdDeviation="1.2" flood-color="#3d352d" flood-opacity="0.35"/>',
        "      </filter>",
        "    </g>",
        '    <clipPath id="landClip"><path d="' + land_path + '"/></clipPath>',
        '    <g id="deftemp"><g id="featurePaths"><path id="feature_1" d="'
        + land_path
        + '"/></g><g id="textPaths"/><g id="statePaths">'
        + "".join(state_clip_paths)
        + '</g><g id="defs-emblems"/><g id="good-icons"/></g>',
        '    <pattern id="oceanicHerringbone" width="28" height="18" patternUnits="userSpaceOnUse">',
        '      <path d="M0 0 L14 8 L28 0 M0 9 L14 17 L28 9" fill="none" stroke="#e6dfc6" stroke-width="1.8" opacity="0.55"/>',
        '      <path d="M0 3 L14 11 L28 3 M0 12 L14 20 L28 12" fill="none" stroke="#9fb1a6" stroke-width="0.7" opacity="0.24"/>',
        "    </pattern>",
        _preview_burg_symbols(),
        "  </defs>",
        f'  <g id="viewbox" shape-rendering="{html.escape(shape_rendering)}" style="cursor: default;">',
        f'    <g id="ocean"><g id="oceanLayers" filter="" layers="-6,-4,-2"><rect id="oceanBase" width="{width}" height="{height}" fill="#c8d4c6"/><rect id="oceanicPattern" width="{width}" height="{height}" fill="url(#oceanicHerringbone)" opacity="0.55"/><path d="{ocean_ring_3}" fill="#e6ead9" opacity="0.14"/><path d="{ocean_ring_2}" fill="#dfe7d8" opacity="0.18"/><path d="{ocean_ring_1}" fill="#d7e1d2" opacity="0.22"/></g><g id="oceanPattern"/></g>',
        '    <g id="lakes"><g id="freshwater"/><g id="salt"/><g id="sinkhole"/><g id="frozen"/><g id="lava"/><g id="dry"/></g>',
        f'    <g id="landmass" opacity="1" fill="#e3dfce"><path d="{land_path}" fill="#d4c3a2" opacity="0.28" transform="translate(3 5)"/><path d="{land_path}" fill="#e3dfce"/></g>',
        f'    <g id="texture" opacity="0.6" filter="" mask="" data-x="0" data-y="0" data-href="./images/textures/antique-small.jpg"{clip_attr}><path d="{land_path}" fill="#f4edda" opacity="0.18" filter="url(#paper)"/></g>',
        '    <g id="terrs"><g id="oceanHeights" data-render="0" opacity="1" scheme="light" terracing="0" skip="0" relax="1" curve="curveBasisClosed" filter="url(#filter-sepia)"/><g id="landHeights" opacity="1" scheme="light" terracing="0" skip="2" relax="1" curve="curveBasisClosed" filter="url(#filter-sepia)"/></g>',
        '    <g id="biomes"/>',
        '    <g id="cells" stroke="#808080" stroke-width="0.1" fill="none">',
    ]
    if render_cells_layer:
        lines.extend(f'      <path d="{path}"/>' for path in cell_layer_paths)
    lines.extend(
        [
            "    </g>",
            '    <g id="gridOverlay"/>',
            '    <g id="coordinates"/>',
            '    <g id="compass"/>',
            f'    <g id="rivers"{clip_attr} fill="#a69b7d" opacity="0.35">',
            _decorative_rivers(width, height),
            "    </g>",
            f'    <g id="terrain"{clip_attr} style="display:none"/>',
            '    <g id="relig"/>',
            '    <g id="cults"/>',
            f'    <g id="regions"{clip_attr}>',
            '      <g id="statesBody" opacity="0.2">',
        ]
    )
    if render_state_fill:
        for state in states[1:]:
            if not isinstance(state, dict):
                continue
            path = state_paths.get(state["i"])
            if not path:
                continue
            color = html.escape(state.get("color", "#d0d7de"))
            lines.append(
                f'        <path id="state{state["i"]}" d="{path}" fill="{color}"/>'
            )
    if render_state_fill and render_state_halo:
        lines.append('      </g><g id="statesHalo" opacity="0.4" data-width="10" stroke-width="10" filter="blur(6px)">')
        for state in states[1:]:
            if not isinstance(state, dict):
                continue
            path = state_paths.get(state["i"])
            if not path:
                continue
            color = _darken_hex(str(state.get("color", "#999999")), 0.78)
            lines.append(
                f'        <path id="state-border{state["i"]}" d="{path}" clip-path="url(#state-clip{state["i"]})" stroke="{color}" fill="none"/>'
            )
    else:
        lines.append('      </g><g id="statesHalo" opacity="0" data-width="0" stroke-width="0" filter="none" style="display:none">')
    lines.extend(
        [
            "      </g>",
            "    </g>",
        ]
    )
    if render_province_labels:
        lines.append(
            f'    <g id="provs" opacity="0.7" fill="#000000" font-size="10" font-family="Georgia" filter=""{clip_attr}><g id="provincesBody"/><g id="provinceLabels" style="display:none">'
        )
        for province in provinces[1:80]:
            if not isinstance(province, dict):
                continue
            x, y = _label_point(province, province_rects)
            lines.append(f'      <text x="{x:.2f}" y="{y:.2f}" id="provinceLabel{province["i"]}">{html.escape(str(province.get("name", "")))}</text>')
        lines.append("    </g></g>")
    else:
        lines.append('    <g id="provs" opacity="0.7" fill="#000000" font-size="10" font-family="Georgia"/>')
    lines.extend(
        [
            '    <g id="zones" opacity="0.6" stroke="#333333" stroke-width="0" stroke-linecap="butt"/>',
            f'    <g id="borders"{clip_attr} fill="none"><g id="stateBorders" opacity="0.8" stroke="#56566d" stroke-width="1" stroke-dasharray="2" stroke-linecap="butt">',
        ]
    )
    if state_border_path:
        lines.append(f'      <path d="{state_border_path}" fill="none"/>')
    lines.append('    </g><g id="provinceBorders" opacity="0.8" stroke="#56566d" stroke-width="0.2" stroke-dasharray="1" stroke-linecap="butt">')
    if province_border_path:
        lines.append(f'      <path d="{province_border_path}" fill="none"/>')
    lines.extend(["    </g></g>", f'    <g id="routes"{clip_attr} fill="none"><g id="roads" opacity="0.7" stroke="#8d502a" stroke-width="0.8" stroke-dasharray="3" stroke-linecap="inherit">'])
    for route in routes:
        points_for_route = route.get("points") if isinstance(route, dict) else None
        if not points_for_route or len(points_for_route) < 2:
            continue
        start, end = points_for_route[0], points_for_route[-1]
        path = _route_curve(float(start[0]), float(start[1]), float(end[0]), float(end[1]), int(route["i"]))
        lines.append(f'      <path id="route{route["i"]}" d="{path}"/>')
    lines.extend(
        [
            '    </g><g id="trails" opacity="0.7" stroke="#8d502a" stroke-width="0.5" stroke-dasharray="1 2" stroke-linecap="butt"/><g id="searoutes" opacity="0.8" stroke="#aa7658" stroke-width="0.6" stroke-dasharray="2 2" stroke-linecap="butt"/></g>',
            '    <g id="temperature"/>',
            f'    <g id="coastline"><g id="sea_island" opacity="1" stroke="#c1a884" stroke-width="0.8" filter="none" auto-filter="0" fill="none"><use href="#feature_1" data-f="1"/></g><g id="lake_island"/></g>',
            '    <g id="ice" opacity="0.35" fill="#e8f0f6" stroke="#e8f0f6" stroke-width="3" filter="url(#dropShadow05)"/>',
            precipitation_layer,
            '    <g id="population"/>',
            '    <g id="goods" style="display:none"><g id="goodsCells"/><g id="goodsIcons"/><g id="goodsBurgs"/></g>',
            '    <g id="markets"/>',
            '    <g id="emblems" style="display:none"><g id="burgEmblems"/><g id="provinceEmblems"/><g id="stateEmblems"/></g>',
            f'    <g id="icons"{clip_attr}><g id="burgIcons">',
        ]
    )
    active_burgs = [b for b in burgs[1:] if isinstance(b, dict) and not b.get("removed")]
    capped_burgs = active_burgs[:max_burg_icons]
    for group in _burg_group_render_order():
        attrs = _burg_icon_attrs(group)
        lines.append(f'      <g id="{group}"{_burg_icon_initial_class(group)} {attrs}>')
        for burg in (b for b in capped_burgs if b.get("group", "town") == group):
            icon = _app_icon_for_group(group)
            lines.append(
                f'        <use id="burg{burg["i"]}" data-id="{burg["i"]}" href="{icon}" x="{burg["x"]:.2f}" y="{burg["y"]:.2f}"/>'
            )
        lines.append("      </g>")
    lines.extend(
        [
            '    </g><g id="anchors"/></g>',
            f'    <g id="labels"{clip_attr}>',
            '      <g id="states" opacity="1" fill="#3e3e4b" stroke="#3a3a3a" stroke-width="0" style="text-shadow: white 0px 0px 4px" letter-spacing="0" data-size="34" font-size="34" font-family="Great Vibes" filter="url(#filter-sepia)" text-anchor="middle">',
        ]
    )
    for state in states[1:]:
        if not isinstance(state, dict):
            continue
        x, y = _label_point(state, state_rects)
        lines.append(
            f'        <text id="stateLabel{state["i"]}" x="{x:.2f}" y="{y:.2f}" transform="rotate({_label_angle(state["i"])},{x:.2f},{y:.2f})">{html.escape(str(state.get("name", "")))}</text>'
        )
    lines.extend(
        [
            "      </g>",
            '      <g id="addedLabels" opacity="1" fill="#3e3e4b" stroke="#3a3a3a" stroke-width="0" style="text-shadow: white 0px 0px 4px" letter-spacing="0" data-size="18" font-size="18" font-family="Times New Roman" filter="url(#filter-sepia)"/>',
            '      <g id="burgLabels">',
        ]
    )
    labelled_burgs = _labelled_burgs(active_burgs, min(220, max_burg_icons))
    for group in _burg_group_render_order():
        lines.append(f'        <g id="{group}"{_burg_group_initial_class(group)} {_burg_label_attrs(group)}>')
        for burg in (b for b in labelled_burgs if b.get("group", "town") == group):
            lines.append(
                f'          <text text-rendering="optimizeSpeed" id="burgLabel{burg["i"]}" data-id="{burg["i"]}" x="{burg["x"]:.2f}" y="{burg["y"]:.2f}" dx="0em" dy="0.85em">{html.escape(str(burg.get("name", "")))}</text>'
            )
        lines.append("        </g>")
    lines.extend(
        [
            "      </g>",
            "    </g>",
            '    <g id="armies"/>',
            '    <g id="markers"/>',
            '    <g id="tradeAnimation"/>',
            '    <g id="ruler"/>',
            '    <g id="fogging"/>',
            '    <g id="debug"/>',
            "  </g>",
            '  <g id="scaleBar" opacity="1" fill="#3e3e4b" font-size="10" data-bar-size="2" data-x="99" data-y="99"/>',
            '  <g id="legend" data-size="13" font-size="13" font-family="Almendra SC" stroke="#812929" stroke-width="2.5" stroke-dasharray="0 4 10 4" stroke-linecap="round" data-x="99" data-y="93" data-columns="8"/>',
            '  <g id="vignette" style="display:none"/>',
            "</svg>",
        ]
    )
    return "\n".join(lines)


def _phase_precipitation_layer(glyphs: list[dict[str, Any]]) -> str:
    lines = [
        '    <g id="prec" opacity="0.9" fill="#2f75b5" stroke="#1f496d" stroke-width="0.65" style="display:block">',
        '      <g id="phasePrecipitation" data-layer="open-targets-max-phase">',
    ]
    for glyph in glyphs:
        x = float(glyph.get("x", 0))
        y = float(glyph.get("y", 0))
        radius = float(glyph.get("r", 3))
        phase = max(0, min(4, int(glyph.get("phase", 0))))
        title = html.escape(str(glyph.get("title") or ""))
        lines.append(
            f'        <circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="none"><title>{title}</title></circle>'
        )
        if phase == 4:
            lines.append(f'        <circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="#2f75b5" opacity="0.74"/>')
        elif phase > 0:
            lines.append(
                f'        <path d="{_sector_path(x, y, radius, phase / 4)}" fill="#2f75b5" opacity="0.74"/>'
            )
    lines.extend(["      </g>", "    </g>"])
    return "\n".join(lines)


def _sector_path(cx: float, cy: float, radius: float, fraction: float) -> str:
    start = -math.pi / 2
    end = start + math.tau * fraction
    x1 = cx + math.cos(start) * radius
    y1 = cy + math.sin(start) * radius
    x2 = cx + math.cos(end) * radius
    y2 = cy + math.sin(end) * radius
    large_arc = 1 if fraction > 0.5 else 0
    return f"M{cx:.2f},{cy:.2f} L{x1:.2f},{y1:.2f} A{radius:.2f},{radius:.2f} 0 {large_arc} 1 {x2:.2f},{y2:.2f} Z"


def _preview_burg_symbols() -> str:
    return """
    <symbol id="icon-watabou-capital" viewBox="0 0 100 100" width="1em" height="1em" overflow="visible">
      <g transform="translate(-60 -194) scale(2 2)">
        <path fill="#EBE8DF" d="M26 90H13l1.3-37.3-1-1v-16h12.6v16l-1 1L26 90" />
        <path d="m19.5 12 1.3 6.9 1 3.8 1 3 1.5 3.6 3.1 6.4H11.6l3.1-6.4 1.5-3.6 1-3 1-3.8 1.3-7" />
        <path fill="#4D3F36" d="M19.5 10.4V5.6L21.3 4l1-.3 1 .5.9 1 1 1.7.9 1 .9.5.9-.3.9-.8.7-.5.8-.2.6.2.5.5.6.4.7.3 1 .1h1.8l-1.8.6-1 .1H32l-.6-.2L31 8h-.6l-.8.4-.7.7-1 1.1-.8.5-1-.1-.9-.8-1-1.4-.9-.7-.9-.2-1 .6-1.8 2.2" />
        <path fill="#4D3F36" d="M19.5 12V5.5" />
        <path fill="#4D3F36" d="M17.2 46h1.6V42l-.3-.6h-1l-.3.6v4" />
        <path fill="#EBE8DF" d="M41.7 90H31.2l1-24.5-.8-.9v-16h10.1v16l-.8.9 1 24.5" />
        <path d="m36.5 29.7 1 5.6.8 3 .8 2.4 1.2 2.9 2.5 5H30.2l2.5-5 1.2-3 .8-2.3.7-3 1-5.6" />
        <path fill="#4D3F36" d="M36.5 28.2v-4.8l1.5-2 .9-.4.7.4.6 1 .7 1.7.7 1.1.8.5.7-.1.8-.7 1-.4h1l1 .2 1.2.5 1 .4 1 .3h2.4l-1.5.5-1 .2h-1.9l-1.2-.3-1 .1-1 .4-1 .7-.8.9-.7.3-.8-.2-.7-1-.7-1.4-.6-.8-.7-.2-.9.7-1.5 2.4" />
        <path fill="#4D3F36" d="M36.5 29.7v-6.3" />
        <path fill="#4D3F36" d="M34 59h1.6V55l-.3-.7h-1l-.3.7V59" />
        <path fill="#4D3F36" d="M47.6 88.8h1.6v-4.1l-.4-.7h-1l-.2.7v4.1" />
        <path fill="#EBE8DF" d="M14.8 94.6H1.5L2 84.4 8.3 73l6.3 11.4.2 10.2m8.3 0h-8.3l-.2-10.2L8.3 73l2 .4h4l2-.4 6.3 11.4.5 10.2" />
        <path d="M22.6 84.4h-8L8.3 73l2 .4h4l2-.4 6.3 11.4" />
        <path fill="#4D3F36" d="M9.5 94.6H7V89l.5-1H9l.5 1v5.5" />
        <path fill="#EBE8DF" d="M50.4 95.3H33.1l.5-10.4L42 70l8.3 15 .2 10.3m8.3 0h-8.3l-.2-10.4L41.9 70l2 .5 2 .1 2-.1 2-.5 8.3 15 .5 10.3" />
        <path d="M58.2 85h-8l-8.3-15 2 .5 2 .1 2-.1 2-.5 8.3 15" />
        <path fill="#4D3F36" d="M43 95.3h-2.3v-5.5l.5-1h1.4l.5 1v5.5" />
        <path fill="#EBE8DF" d="M27.9 97.3H13.4l1-19.8L21 65.8l6.5 11.7.5 19.8m8.5 0h-8.5l-.5-19.8-6.5-11.7 2 .4 2 .1 2-.1 2-.4 6.5 11.7 1 19.8" />
        <path d="M35.4 77.5h-8l-6.5-11.7 2 .4 2 .1 2-.1 2-.4 6.5 11.7" />
        <path fill="#4D3F36" d="m21.6 77.1.1.4-.1.4-.3.3-.4.1h-.4l-.3-.4v-.8l.3-.3h.8l.3.3" />
        <path fill="#4D3F36" d="M22.1 97.3h-2.4v-5.5l.5-1h1.4l.5 1v5.5" />
      </g>
      <circle fill="#EBE8DF" stroke-width="3" cx="0" cy="0" r="10" />
    </symbol>
    <symbol id="icon-watabou-city" viewBox="0 0 100 100" width="1em" height="1em" overflow="visible">
      <g transform="translate(-60 -150) scale(2 2)">
        <path fill="#EBE8DF" d="M29.5 70H18L19 48.7l-.9-.9v-16h11v16l-.8 1L29.5 70" />
        <path d="m23.7 11 1.2 6.2.8 3.3 1 2.6 1.2 3.1 2.8 5.6H16.8l2.8-5.6 1.3-3.1.9-2.6.8-3.3 1.1-6.1" />
        <path fill="#4D3F36" d="M23.7 9.6V4.8l1.4-.7h.9l.8.3 1 .7 1.1 1 1 .6.9.2.7-.4.6-.7.7-.4h.7l.7.3.8.8.8.5.9.3h1l2-.1-2 .8-1 .2h-.9l-.8-.3-.8-.5-.7-.1-.7.2-.7.6-.6 1-.7.5h-.9l-1-.2-1-.7-1-.4-1-.1-.8.3-1.4 1M23.7 11V4.9M23 42.2h1.5v-4.1l-.3-.7h-1l-.3.7v4.1" />
        <path fill="#EBE8DF" d="M19 71.2H1.5L2 63l4-15 4.2.4 4.2.1 4.2-.1 4.1-.5-4 15 .2 8.3M2 63h16.7m8.4 8.2H19l-.2-8.2 4-15 4 15 .4 8.2" />
        <path d="M18.7 63H2l4-15 4.2.4 4.2.1 4.2-.1 4.1-.5-4 15" />
        <path fill="#4D3F36" d="M9.6 69.5h1.6v-4.2l-.3-.6h-1l-.3.6v4.2" />
        <path fill="#EBE8DF" d="M49.4 71.8H32.5l.5-8.9 4-14.6 4 .5 4.1.1 4-.1 4.1-.5-4 14.6.2 8.9M33 62.9h16.2m8.5 8.9h-8.3l-.2-8.9 4-14.6 4 14.6.5 8.9" />
        <path d="M49.2 63H33l4-14.7 4 .5 4.1.1 4-.1 4.1-.5-4 14.6" />
        <path fill="#4D3F36" d="M40.3 69.8h1.6v-4.2l-.3-.6h-1l-.3.6v4.2" />
        <path fill="#EBE8DF" d="M32.6 75.3H15.9l1-19 7.6-13.6 7.6 13.6.5 19m8.5 0h-8.5l-.5-19-7.6-13.6 2 .4 2 .1 2-.1 2-.5 7.6 13.8 1 19" />
        <path d="M40.1 56.4h-8l-7.6-13.8 2 .5 2 .1 2-.1 2-.5 7.6 13.8" />
        <path fill="#4D3F36" d="m25.2 56 .1.4-.1.4-.3.2-.4.1h-.4l-.3-.4-.1-.4.1-.3.3-.3.4-.2.4.2.3.3M25.7 75.3h-2.4V70l.5-1h1.4l.5 1v5.4" />
      </g>
      <circle fill="#EBE8DF" stroke-width="3" cx="0" cy="0" r="10" />
    </symbol>
    <symbol id="icon-watabou-town" viewBox="0 0 100 100" width="1em" height="1em" overflow="visible">
      <g transform="translate(0 -10) scale(2 2)">
        <path fill="#EBE8DF" d="M18.9-2H2.6l.5-9 7.8-14 7.8 14 .2 9M27-2H19l-.2-9-7.8-14 2 .4 2 .1 2-.1 2-.5 7.8 14L27-2 Z" />
        <path d="M26.7-11h-8l-7.8-14 2 .4 2 .1 2-.1 2-.5 7.8 14" />
        <path fill="#4D3F36" stroke="none" d="M12-2H9.8v-5.4l.4-1h1.5l.5 1V-2" />
        <path fill="#EBE8DF" d="M-10.3.4h-19.6l.4-8 4-17.2 4.8.5 4.7.2 4.8-.2 4.7-.5-4 17.1.2 8m-19.2-8h19m8.4 8h-8.2l-.2-8 4-17 4 17 .4 8Z" />
        <path d="M-10.5-7.7h-19l4-17 4.8.4 4.7.2 4.8-.2 4.7-.5-4 17.1" />
        <path fill="#4D3F36" stroke="none" d="M-24-1.3h1.7v-4.1l-.4-.7h-1l-.2.7v4.1" />
        <path fill="#EBE8DF" d="M-1.4 5H-17l.8-15 7.2-13.1 7.3 13 .4 15.2M7 5h-8.4L-1.8-10-9-23.1l2 .3 2 .2 2-.2 2-.3 7.3 13L7 4 Z" />
        <path d="M6.2-10h-8L-9-23.1l2 .3 2 .2 2-.2 2-.3 7.3 13" />
        <path fill="#4D3F36" stroke="none" d="M-7.9 5h-2.4V-.3l.5-1h1.5l.4 1v5.5" />
      </g>
      <circle fill="#EBE8DF" stroke-width="3" cx="0" cy="0" r="10" />
    </symbol>
    <symbol id="icon-watabou-village" viewBox="0 0 100 100" width="1em" height="1em" overflow="visible">
      <g transform="translate(0 -6) scale(2 2)">
        <path d="M 9.778,-3.849 L -3.296,-3.849 L -2.723,-15.318 L 3.384,-26.311 L 9.491,-15.318 L 9.778,-3.849 M 18.065,-3.849 L 9.778,-3.849 L 9.491,-15.318 L 3.384,-26.311 L 5.384,-25.981 L 7.384,-25.871 L 9.384,-25.981 L 11.384,-26.311 L 17.491,-15.318 L 18.065,-3.849" fill="#EBE8DF" />
        <path d="M 17.491,-15.318 L 9.491,-15.318 L 3.384,-26.311 L 5.384,-25.981 L 7.384,-25.871 L 9.384,-25.981 L 11.384,-26.311 L 17.491,-15.318" />
        <path d="M 4.584,-3.849 L 2.184,-3.849 L 2.184,-9.289 L 2.664,-10.249 L 4.104,-10.249 L 4.584,-9.289 L 4.584,-3.849" fill="#4D3F36" />
        <path d="M -5.555,2.988 L -20.357,2.988 L -19.872,-6.711 L -15.872,-19.379 L -12.354,-18.999 L -8.835,-18.872 L -5.316,-18.999 L -1.797,-19.379 L -5.797,-6.711 L -5.555,2.988 M -19.872,-6.711 L -5.797,-6.711 M 2.688,2.988 L -5.555,2.988 L -5.797,-6.711 L -1.797,-19.379 L 2.203,-6.711 L 2.688,2.988" fill="#EBE8DF" />
        <path d=" M -5.797,-6.711 L -19.872,-6.711 L -15.872,-19.379 L -12.354,-18.999 L -8.835,-18.872 L -5.316,-18.999 L -1.797,-19.379 L -5.797,-6.711" />
        <path d="M -13.635,0.539 L -12.035,0.539 L -12.035,-3.621 L -12.355,-4.261 L -13.315,-4.261 L -13.635,-3.621 L -13.635,0.539" fill="#4D3F36" />
      </g>
      <circle fill="#EBE8DF" stroke-width="3" cx="0" cy="0" r="10" />
    </symbol>
    <symbol id="icon-watabou-hamlet" viewBox="0 0 100 100" width="1em" height="1em" overflow="visible">
      <g transform="translate(-120 -95) scale(2 2)">
        <path fill="#EBE8DF" d="M63 48H48.6l.4-8.7 6.8-12.2 6.8 12.2.2 8.7m8.3 0h-8.3l-.2-8.7L56 27.1l2 .3 2 .2 2-.2 2-.3 6.8 12.2.5 8.7" />
        <path d="M70.7 39.3h-8L56 27.1l2 .3 2 .2 2-.2 2-.3 6.8 12.2" />
        <path fill="#4D3F36" d="M57.1 48h-2.4v-5.4l.5-1h1.4l.5 1V48" />
      </g>
      <circle fill="#EBE8DF" stroke-width="3" cx="0" cy="0" r="10" />
    </symbol>
    """.strip()


def _burg_group_render_order() -> list[str]:
    return ["hamlet", "village", "town", "city", "capital"]


def _app_icon_for_group(group: str) -> str:
    return {
        "capital": "#icon-watabou-capital",
        "city": "#icon-watabou-city",
        "town": "#icon-watabou-town",
        "village": "#icon-watabou-village",
        "hamlet": "#icon-watabou-hamlet",
    }.get(group, "#icon-watabou-town")


def _burg_group_min_zoom(group: str) -> int:
    return {"capital": 1, "city": 4, "town": 6, "village": 10, "hamlet": 14}.get(group, 6)


def _burg_group_initial_class(group: str) -> str:
    return "" if _burg_group_min_zoom(group) <= 1 else ' class="hidden"'


def _burg_icon_initial_class(_group: str) -> str:
    return ""


def _burg_icon_attrs(group: str) -> str:
    opacity = "0.9" if group == "hamlet" else "1"
    min_zoom = _burg_group_min_zoom(group)
    return (
        f'data-icon="{_app_icon_for_group(group)}" data-minZoom="{min_zoom}" opacity="{opacity}" fill="#E59189" fill-opacity="1" '
        'font-size="2" stroke="#4D3F36" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'
    )


def _burg_label_attrs(group: str) -> str:
    size = {"capital": 6, "city": 5, "town": 3, "village": 3, "hamlet": 2}.get(group, 3)
    min_zoom = _burg_group_min_zoom(group)
    return (
        'opacity="0.9" fill="#3e3e4b" style="text-shadow: white 0px 0px 4px" letter-spacing="0" '
        f'data-size="{size}" data-minZoom="{min_zoom}" font-size="{size}" font-family="UnifrakturMaguntia" data-dy="0.85"'
    )


def _label_point(item: dict[str, Any], rects: dict[int, tuple[float, float, float, float]]) -> tuple[float, float]:
    pole = item.get("pole")
    if isinstance(pole, (list, tuple)) and len(pole) >= 2:
        return float(pole[0]), float(pole[1])
    rect = rects.get(int(item.get("i", 0)))
    if rect:
        x, y, w, h = rect
        return x + w / 2, y + h / 2
    return 0.0, 0.0


def _darken_hex(value: str, factor: float) -> str:
    if not value.startswith("#") or len(value) != 7:
        return "#666666"
    try:
        r = int(value[1:3], 16)
        g = int(value[3:5], 16)
        b = int(value[5:7], 16)
    except ValueError:
        return "#666666"
    return f"#{max(0, min(255, round(r * factor))):02x}{max(0, min(255, round(g * factor))):02x}{max(0, min(255, round(b * factor))):02x}"


def _labelled_burgs(burgs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    priority = {"capital": 0, "city": 1, "town": 2, "village": 3, "hamlet": 4}
    sorted_burgs = sorted(
        burgs,
        key=lambda burg: (
            priority.get(str(burg.get("group", "town")), 2),
            -float(burg.get("population", 0)),
            int(burg.get("i", 0)),
        ),
    )
    return sorted_burgs[:limit]


def color_for_id(value: str, saturation: float = 0.43, lightness: float = 0.62) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    hue = int(digest[:6], 16) / 0xFFFFFF
    return _hsl_to_hex(hue, saturation, lightness)


def related_color_for_id(base_color: str, value: str, *, index: int = 0, count: int = 1) -> str:
    """Return a deterministic color in the same visual family as base_color.

    FMG uses getMixedColor(state.color) for provinces. This keeps the same idea
    but avoids random output: province hue stays close to the state hue, while
    lightness and saturation vary enough for adjacent provinces to be readable.
    """

    base = _hex_to_hls(base_color)
    if base is None:
        return color_for_id(value, saturation=0.35, lightness=0.7)

    hue, lightness, saturation = base
    spread = math.log1p(max(1, count))
    hue_span = min(0.045, 0.014 + spread * 0.006)
    lightness_span = min(0.13, 0.055 + spread * 0.012)
    phase = (index * 0.61803398875 + _unit(f"province-color-phase:{value}", 0)) % 1

    hue = (hue + (_unit(f"province-color-hue:{value}", 0) - 0.5) * 2 * hue_span) % 1
    lightness = _clamp(lightness + 0.065 + (phase - 0.5) * 2 * lightness_span, 0.5, 0.84)
    saturation = _clamp(saturation * (0.82 + _unit(f"province-color-sat:{value}", 0) * 0.24), 0.18, 0.62)
    return _hsl_to_hex(hue, saturation, lightness)


def stable_int(value: str, modulo: int = 10**9) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:12], 16) % modulo


def _blob_path(cx: float, cy: float, rx: float, ry: float, seed: str, points: int, roughness: float) -> str:
    coords: list[tuple[float, float]] = []
    for i in range(points):
        angle = math.tau * i / points
        wave = math.sin(angle * 3 + _unit(seed, i) * math.tau) * 0.04
        noise = (_unit(seed, i + 1000) - 0.5) * roughness
        radius = 1 + wave + noise
        x = cx + math.cos(angle) * rx * radius
        y = cy + math.sin(angle) * ry * radius
        coords.append((x, y))
    return _polygon_path(coords)


def _organic_rect_path(
    x: float, y: float, w: float, h: float, seed: str, steps_per_side: int, roughness: float
) -> str:
    coords: list[tuple[float, float]] = []
    inset_x = min(w * 0.12, 18)
    inset_y = min(h * 0.12, 18)
    for i in range(steps_per_side + 1):
        t = i / steps_per_side
        coords.append(_jitter_point(x + t * w, y, w, h, inset_x, inset_y, seed, len(coords), roughness))
    for i in range(1, steps_per_side + 1):
        t = i / steps_per_side
        coords.append(_jitter_point(x + w, y + t * h, w, h, inset_x, inset_y, seed, len(coords), roughness))
    for i in range(1, steps_per_side + 1):
        t = i / steps_per_side
        coords.append(_jitter_point(x + (1 - t) * w, y + h, w, h, inset_x, inset_y, seed, len(coords), roughness))
    for i in range(1, steps_per_side):
        t = i / steps_per_side
        coords.append(_jitter_point(x, y + (1 - t) * h, w, h, inset_x, inset_y, seed, len(coords), roughness))
    return _polygon_path(coords)


def _rect_path(x: float, y: float, w: float, h: float) -> str:
    return _polygon_path([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def _cell_layer_paths(width: int, height: int, grid: dict[str, Any]) -> list[str]:
    points = grid.get("points") or []
    if not points:
        return []

    cells_x = int(grid["cellsX"])
    cells_y = int(grid["cellsY"])
    spacing = float(grid["spacing"])
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    max_chunk_length = 240_000

    for cell in range(len(points)):
        polygon = _cell_polygon(cell, points, cells_x, cells_y, width, height, spacing)
        if len(polygon) < 3:
            continue
        path = _compact_polygon_path(polygon)
        current.append(path)
        current_length += len(path)
        if current_length >= max_chunk_length:
            chunks.append("".join(current))
            current = []
            current_length = 0

    if current:
        chunks.append("".join(current))
    return chunks


def _cell_polygon(
    cell: int,
    points: list[list[float]],
    cells_x: int,
    cells_y: int,
    width: int,
    height: int,
    spacing: float,
) -> list[tuple[float, float]]:
    px, py = points[cell]
    row, col = divmod(cell, cells_x)
    margin = spacing * 3.0
    polygon = [
        (max(0.0, px - margin), max(0.0, py - margin)),
        (min(float(width), px + margin), max(0.0, py - margin)),
        (min(float(width), px + margin), min(float(height), py + margin)),
        (max(0.0, px - margin), min(float(height), py + margin)),
    ]

    neighbours: list[tuple[float, int]] = []
    for neighbour_row in range(max(0, row - 2), min(cells_y, row + 3)):
        for neighbour_col in range(max(0, col - 2), min(cells_x, col + 3)):
            neighbour = neighbour_row * cells_x + neighbour_col
            if neighbour == cell or neighbour >= len(points):
                continue
            qx, qy = points[neighbour]
            neighbours.append(((qx - px) ** 2 + (qy - py) ** 2, neighbour))

    for _, neighbour in sorted(neighbours):
        qx, qy = points[neighbour]
        polygon = _clip_to_closer_seed(polygon, px, py, qx, qy)
        if len(polygon) < 3:
            return []

    return polygon


def _clip_to_closer_seed(
    polygon: list[tuple[float, float]],
    px: float,
    py: float,
    qx: float,
    qy: float,
) -> list[tuple[float, float]]:
    a = 2 * (qx - px)
    b = 2 * (qy - py)
    c = qx * qx + qy * qy - px * px - py * py
    clipped: list[tuple[float, float]] = []

    def inside(point: tuple[float, float]) -> bool:
        return a * point[0] + b * point[1] <= c + 1e-7

    def intersection(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
        sx, sy = start
        ex, ey = end
        denominator = a * (ex - sx) + b * (ey - sy)
        if abs(denominator) < 1e-12:
            return end
        t = (c - a * sx - b * sy) / denominator
        t = max(0.0, min(1.0, t))
        return sx + (ex - sx) * t, sy + (ey - sy) * t

    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                clipped.append(intersection(previous, current))
            clipped.append(current)
        elif previous_inside:
            clipped.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside

    return clipped


def _compact_polygon_path(coords: list[tuple[float, float]]) -> str:
    return "M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in coords) + "Z"


def _region_fill_paths(regions: list[int], grid: dict[str, Any]) -> dict[int, str]:
    paths: dict[int, str] = {}
    for region in sorted({region for region in regions if region}):
        loops = _region_boundary_loops(regions, grid, region)
        parts: list[str] = []
        for loop in loops:
            if len(loop) < 4:
                continue
            coords = [_vertex_point(vertex, grid, f"fill:{region}", 0.1) for vertex in loop[:-1]]
            coords = _chaikin_closed(coords, 2)
            path = _polygon_path(coords)
            if path:
                parts.append(path)
        if parts:
            paths[region] = " ".join(parts)
    return paths


def _region_boundary_loops(regions: list[int], grid: dict[str, Any], region: int) -> list[list[tuple[int, int]]]:
    cells_x = int(grid["cellsX"])
    cells_y = int(grid["cellsY"])
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def cell(row: int, col: int) -> int:
        return row * cells_x + col

    def same(row: int, col: int) -> bool:
        if row < 0 or row >= cells_y or col < 0 or col >= cells_x:
            return False
        index = cell(row, col)
        return index < len(regions) and regions[index] == region

    for row in range(cells_y):
        for col in range(cells_x):
            index = cell(row, col)
            if index >= len(regions) or regions[index] != region:
                continue
            if not same(row - 1, col):
                edges.add(((col, row), (col + 1, row)))
            if not same(row, col + 1):
                edges.add(((col + 1, row), (col + 1, row + 1)))
            if not same(row + 1, col):
                edges.add(((col + 1, row + 1), (col, row + 1)))
            if not same(row, col - 1):
                edges.add(((col, row + 1), (col, row)))

    by_start: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for start, end in edges:
        by_start.setdefault(start, []).append(end)
    for starts in by_start.values():
        starts.sort()

    loops: list[list[tuple[int, int]]] = []
    remaining = set(edges)
    while remaining:
        start, end = min(remaining)
        remaining.remove((start, end))
        loop = [start, end]
        while end != start:
            choices = [candidate for candidate in by_start.get(end, []) if (end, candidate) in remaining]
            if not choices:
                break
            previous = loop[-2]
            next_end = _choose_next_boundary_vertex(previous, end, choices)
            remaining.remove((end, next_end))
            loop.append(next_end)
            end = next_end
        if loop[-1] == loop[0]:
            loops.append(loop)
    return loops


def _cell_border_path(
    regions: list[int],
    grid: dict[str, Any],
    seed: str,
    *,
    same_state: list[int] | None = None,
) -> str:
    cells_x = int(grid["cellsX"])
    cells_y = int(grid["cellsY"])
    segments: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def cell(row: int, col: int) -> int:
        return row * cells_x + col

    for row in range(cells_y):
        for col in range(cells_x - 1):
            left = cell(row, col)
            right = cell(row, col + 1)
            if not _is_border_pair(left, right, regions, same_state):
                continue
            segments.add(_ordered_segment((col + 1, row), (col + 1, row + 1)))

    for row in range(cells_y - 1):
        for col in range(cells_x):
            top = cell(row, col)
            bottom = cell(row + 1, col)
            if not _is_border_pair(top, bottom, regions, same_state):
                continue
            segments.add(_ordered_segment((col, row + 1), (col + 1, row + 1)))

    chains = _border_chains(segments)
    parts: list[str] = []
    for chain in chains:
        if len(chain) < 2:
            continue
        closed = chain[0] == chain[-1]
        coords = [_vertex_point(vertex, grid, seed, 0.18) for vertex in chain]
        coords = _chaikin_closed(coords[:-1], 1) + [_chaikin_closed(coords[:-1], 1)[0]] if closed else _chaikin_open(coords, 1)
        parts.append(_polyline_path(coords, closed=closed))
    return " ".join(parts)


def _is_border_pair(left: int, right: int, regions: list[int], same_state: list[int] | None) -> bool:
    if left >= len(regions) or right >= len(regions):
        return False
    left_region = regions[left]
    right_region = regions[right]
    if not left_region or not right_region or left_region == right_region:
        return False
    if same_state is not None and (left >= len(same_state) or right >= len(same_state) or same_state[left] != same_state[right]):
        return False
    return True


def _border_vertex(col: int, row: int, grid: dict[str, Any], seed: str) -> tuple[float, float]:
    return _vertex_point((col, row), grid, seed, 0.22)


def _vertex_point(vertex: tuple[int, int], grid: dict[str, Any], seed: str, roughness: float) -> tuple[float, float]:
    col, row = vertex
    cells_x = int(grid["cellsX"])
    cells_y = int(grid["cellsY"])
    cell_w = float(grid.get("cellWidth") or grid["spacing"])
    cell_h = float(grid.get("cellHeight") or grid["spacing"])
    x = col * cell_w
    y = row * cell_h
    if 0 < col < cells_x and 0 < row < cells_y:
        amplitude = min(cell_w, cell_h) * roughness
        x += (_unit(f"{seed}:vx", col * 100003 + row) - 0.5) * amplitude
        y += (_unit(f"{seed}:vy", col * 100003 + row) - 0.5) * amplitude
    return round(x, 2), round(y, 2)


def _ordered_segment(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return (a, b) if a <= b else (b, a)


def _border_chains(
    segments: set[tuple[tuple[int, int], tuple[int, int]]]
) -> list[list[tuple[int, int]]]:
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for a, b in segments:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    remaining = set(segments)
    starts = sorted((vertex for vertex, neighbors in adjacency.items() if len(neighbors) != 2))
    starts.extend(vertex for vertex in sorted(adjacency) if vertex not in starts)

    chains: list[list[tuple[int, int]]] = []
    for start in starts:
        while True:
            next_vertex = None
            for candidate in sorted(adjacency.get(start, [])):
                if _ordered_segment(start, candidate) in remaining:
                    next_vertex = candidate
                    break
            if next_vertex is None:
                break

            chain = [start, next_vertex]
            remaining.remove(_ordered_segment(start, next_vertex))
            previous, current = start, next_vertex
            while True:
                candidates = [
                    candidate
                    for candidate in adjacency.get(current, [])
                    if candidate != previous and _ordered_segment(current, candidate) in remaining
                ]
                if not candidates:
                    break
                candidate = _choose_next_boundary_vertex(previous, current, sorted(candidates))
                remaining.remove(_ordered_segment(current, candidate))
                chain.append(candidate)
                previous, current = current, candidate
                if current == start:
                    break
            chains.append(chain)
    return chains


def _choose_next_boundary_vertex(
    previous: tuple[int, int], current: tuple[int, int], choices: list[tuple[int, int]]
) -> tuple[int, int]:
    incoming = (current[0] - previous[0], current[1] - previous[1])

    def turn_score(candidate: tuple[int, int]) -> tuple[int, tuple[int, int]]:
        outgoing = (candidate[0] - current[0], candidate[1] - current[1])
        cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
        dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        if cross < 0:
            turn = 0
        elif dot > 0:
            turn = 1
        else:
            turn = 2
        return turn, candidate

    return min(choices, key=turn_score)


def _polyline_path(coords: list[tuple[float, float]], *, closed: bool) -> str:
    if not coords:
        return ""
    commands = [f"M{coords[0][0]:.2f},{coords[0][1]:.2f}"]
    for x, y in coords[1:]:
        commands.append(f"L{x:.2f},{y:.2f}")
    if closed:
        commands.append("Z")
    return " ".join(commands)


def _chaikin_closed(coords: list[tuple[float, float]], iterations: int) -> list[tuple[float, float]]:
    if len(coords) < 3:
        return coords
    current = coords
    for _ in range(iterations):
        refined: list[tuple[float, float]] = []
        for index, p0 in enumerate(current):
            p1 = current[(index + 1) % len(current)]
            refined.append((p0[0] * 0.75 + p1[0] * 0.25, p0[1] * 0.75 + p1[1] * 0.25))
            refined.append((p0[0] * 0.25 + p1[0] * 0.75, p0[1] * 0.25 + p1[1] * 0.75))
        current = refined
    return current


def _chaikin_open(coords: list[tuple[float, float]], iterations: int) -> list[tuple[float, float]]:
    if len(coords) < 3:
        return coords
    current = coords
    for _ in range(iterations):
        refined = [current[0]]
        for p0, p1 in zip(current, current[1:]):
            refined.append((p0[0] * 0.75 + p1[0] * 0.25, p0[1] * 0.75 + p1[1] * 0.25))
            refined.append((p0[0] * 0.25 + p1[0] * 0.75, p0[1] * 0.25 + p1[1] * 0.75))
        refined.append(current[-1])
        current = refined
    return current


def _jitter_point(
    px: float,
    py: float,
    w: float,
    h: float,
    inset_x: float,
    inset_y: float,
    seed: str,
    index: int,
    roughness: float,
) -> tuple[float, float]:
    jitter_x = (_unit(seed, index) - 0.5) * w * roughness
    jitter_y = (_unit(seed, index + 200) - 0.5) * h * roughness
    return px + jitter_x + (inset_x if px == 0 else 0), py + jitter_y + (inset_y if py == 0 else 0)


def _polygon_path(coords: list[tuple[float, float]]) -> str:
    if not coords:
        return ""
    first_x, first_y = coords[0]
    commands = [f"M{first_x:.2f},{first_y:.2f}"]
    for x, y in coords[1:]:
        commands.append(f"L{x:.2f},{y:.2f}")
    commands.append("Z")
    return " ".join(commands)


def _route_curve(x1: float, y1: float, x2: float, y2: float, seed: int) -> str:
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2
    dx = x2 - x1
    dy = y2 - y1
    length = max(1.0, math.hypot(dx, dy))
    offset = ((_unit("route", seed) - 0.5) * 0.22) * length
    cx = mx - dy / length * offset
    cy = my + dx / length * offset
    return f"M{x1:.2f},{y1:.2f} Q{cx:.2f},{cy:.2f} {x2:.2f},{y2:.2f}"


def _decorative_rivers(width: int, height: int) -> str:
    lines = []
    for i, start in enumerate([0.28, 0.47, 0.66]):
        x0 = width * start
        y0 = height * 0.18
        x1 = x0 + width * ((_unit("river", i) - 0.5) * 0.32)
        y1 = height * 0.48
        x2 = x1 + width * ((_unit("river", i + 20) - 0.5) * 0.26)
        y2 = height * 0.83
        lines.append(
            f'      <path d="M{x0:.2f},{y0:.2f} C{x0 + 45:.2f},{height * 0.30:.2f} {x1 - 70:.2f},{y1 - 45:.2f} {x1:.2f},{y1:.2f} S{x2 - 50:.2f},{height * 0.72:.2f} {x2:.2f},{y2:.2f}" fill="#ffffff" fill-opacity="0" stroke="#5f92a2" stroke-width="{1.8 - i * 0.25:.2f}" opacity="0.58"/>'
        )
    return "\n".join(lines)


def _decorative_terrain(width: int, height: int) -> str:
    symbols = []
    for i in range(36):
        x = width * (0.12 + 0.76 * _unit("terrain-x", i))
        y = height * (0.16 + 0.68 * _unit("terrain-y", i))
        size = 5 + 6 * _unit("terrain-s", i)
        if i % 3 == 0:
            symbols.append(
                f'      <path d="M{x - size:.2f},{y + size:.2f} L{x:.2f},{y - size:.2f} L{x + size:.2f},{y + size:.2f} Z" fill="#8b7a58" opacity="0.28"/>'
            )
        else:
            symbols.append(f'      <circle cx="{x:.2f}" cy="{y:.2f}" r="{size / 2:.2f}" fill="#70864f" opacity="0.18"/>')
    return "\n".join(symbols)


def _label_angle(identifier: int) -> float:
    return round((_unit("label", identifier) - 0.5) * 16, 2)


def _unit(seed: str, index: int) -> float:
    return stable_int(f"{seed}:{index}", 10**9) / 10**9


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    import colorsys

    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _hex_to_hls(value: str) -> tuple[float, float, float] | None:
    if not value.startswith("#") or len(value) != 7:
        return None
    try:
        r = int(value[1:3], 16) / 255
        g = int(value[3:5], 16) / 255
        b = int(value[5:7], 16) / 255
    except ValueError:
        return None

    import colorsys

    return colorsys.rgb_to_hls(r, g, b)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _burg_group_options() -> list[dict[str, Any]]:
    return [
        {"name": "capital", "active": True, "order": 9, "features": {"capital": True}, "preview": "watabou-city"},
        {"name": "city", "active": True, "order": 8, "percentile": 90, "min": 5, "preview": "watabou-city"},
        {"name": "town", "active": True, "order": 7, "isDefault": True, "preview": "watabou-city"},
        {"name": "village", "active": True, "order": 2, "min": 0.1, "max": 2, "preview": "watabou-village"},
        {"name": "hamlet", "active": True, "order": 1, "features": {"plaza": False}, "max": 0.1, "preview": "watabou-village"},
    ]


def _csv(values: list[Any]) -> str:
    return ",".join(_format_number(value) for value in values)


def _format_number(value: Any) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _count_csv(value: str) -> int:
    if value == "":
        return 0
    return len(value.split(","))


def _ints(value: str) -> list[int]:
    if not value:
        return []
    return [int(float(part)) for part in value.split(",")]
