# Open Targets to Azgaar Map Converter Specs

## Purpose

Build a Python CLI that converts Open Targets-style biomedical hierarchy data into a valid Azgaar Fantasy Map Generator `.map` file.

The current target input is the flat `states.json` structure:

```json
{
  "provinceId": "EFO_1000096",
  "therapeuticArea": "GO_0008150",
  "therapeuticAreaName": "biological_process",
  "provinceName": "Atrophy",
  "leafId": "EFO_0009851",
  "leafName": "muscle atrophy",
  "populationSize": 0
}
```

The file is newline-delimited JSON even when it uses a `.json` suffix.

## Semantic Mapping

- `therapeuticArea` -> Azgaar `pack.states`
- `provinceId` -> Azgaar `pack.provinces`
- `leafId` -> Azgaar `pack.burgs`
- `populationSize` -> quantitative map metrics
- `culture` -> non-semantic default culture only

Default metric layer mappings for `states.json`:

- elevation: `populationSizeTotal`
- precipitation: `membershipCount`
- biome: `populationSize`
- population: `populationSizeTotal`

## Hierarchy Rules

The converter creates an artificial root node named `__OPEN_TARGETS_ROOT__`.

Edges are derived as:

- `therapeuticArea -> __OPEN_TARGETS_ROOT__`
- `provinceId -> therapeuticArea`
- `leafId -> provinceId`

Each disease leaf is assigned to exactly one primary map location. If a leaf has multiple parents, the resolver chooses a deterministic primary path using:

1. highest descendant count for the candidate parent
2. shortest path
3. lexical id tie-break

Additional direct parents are preserved in manifest metadata as `extra_parents` and `extra_parent_names`.

## Azgaar Save Requirements

The generated `.map` must contain 46 CRLF-delimited save sections in Azgaar order.

Required populated sections include:

- map parameters and settings
- serialized SVG preview
- `grid`
- `grid.cells.h`
- `grid.cells.prec`
- `pack.features`
- `pack.cultures`
- `pack.states`
- `pack.provinces`
- `pack.burgs`
- `pack.cells.*`
- `pack.routes`
- minimal optional lists for religions, goods, markets, notes, markers, rivers, zones, and ice

The converter keeps cultures minimal:

- culture `0`: Wildlands
- culture `1`: Diseases

All generated disease cells, states, provinces, and burgs use culture `1`.

## Layout Requirements

The v1 atlas is all-land so the full disease set can fit predictably within Azgaar's 100k-cell ceiling.

Current sizing rule:

- target cells = max(1000, ceil(disease count * `map.cell_multiplier`))
- default `map.cell_multiplier` = `4.0`, so small/subset maps keep enough non-settlement cells while avoiding excessive packed cell counts
- hard ceiling = `map.max_cells`, default `100000`
- if the full target would exceed the ceiling, the converter uses the ceiling and still requires at least one cell per burg

Saved SVG behavior should match native Azgaar saves as closely as practical:

- `pack.cells.*` always contains the real cell/state/province/burg data.
- visible SVG cell outlines are off by default via `svg.cells_layer: false`.
- state/province fill layers are off by default; the web app can render these from `pack.cells`.
- broad SVG clipping wrappers and state halo filters are off by default.
- visible burg icons are capped by `svg.max_burg_icons`, default `5000`, so large maps do not serialize tens of thousands of SVG nodes.

For the current `states.json`, the converter is expected to build up to:

- 46,773 disease burgs
- 26 states
- 755 primary provinces
- 100,000 cells

Every burg must have:

- valid cell id
- x/y coordinates
- state id
- province id
- unique occupied cell

Every province must belong to an existing state.

## Outputs

For an output path such as:

```bash
outputs/open_targets_states.map
```

the converter writes:

- `outputs/open_targets_states.map`
- `outputs/open_targets_states.manifest.json`
- optional extracted preview files, such as `outputs/open_targets_states_preview.svg`

The manifest maps source ids to Azgaar ids:

- state source id -> Azgaar state id
- province source id -> Azgaar province id
- disease source id -> Azgaar burg id, state id, province id, primary path, alternate parents

## CLI

General config-driven build:

```bash
PYTHONPATH=src python3 -m ot_fmg build \
  --config examples/open_targets_map.example.yml \
  --out outputs/open_targets.map
```

Direct `states.json` build:

```bash
PYTHONPATH=src python3 -m ot_fmg build-states-json \
  --states-json /Users/alegbe/Downloads/states.json \
  --out outputs/open_targets_states.map \
  --name "Open Targets Disease Atlas"
```

Validation:

```bash
PYTHONPATH=src python3 -m ot_fmg validate outputs/open_targets_states.map
```

## Validation Rules

The validator must check:

- exactly 46 CRLF-delimited sections
- JSON sections parse correctly
- serialized SVG exists in section 5
- `grid.cells.*` lengths match grid points
- `pack.cells.*` lengths match grid points
- every burg has a valid, unique cell
- `pack.cells.burg[cell]` mirrors the burg id
- burg ids remain below the `Uint16Array` ceiling of 65,535
- every province references an existing state
- every route has at least two points
