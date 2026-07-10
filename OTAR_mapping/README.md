# Open Targets to Azgaar Map Converter

This workspace contains a Python CLI that converts Open Targets-style disease tables into an Azgaar Fantasy Map Generator `.map` file.

The v1 model is intentionally all-land and uses Azgaar's political hierarchy:

- top disease ontology ancestor -> Azgaar `state`
- second disease ontology ancestor -> Azgaar `province`
- disease -> Azgaar `burg`
- cultures are kept minimal and non-semantic

## Usage

```bash
PYTHONPATH=src python3 -m ot_fmg build --config examples/open_targets_map.example.yml --out outputs/open_targets.map
PYTHONPATH=src python3 -m ot_fmg validate outputs/open_targets.map
```

For the flat `states.json` structure where therapeutic areas are states,
provinces are provinces, and leaves are disease burgs:

```bash
PYTHONPATH=src python3 -m ot_fmg build-states-json \
  --states-json /Users/alegbe/Downloads/states.json \
  --out outputs/open_targets_states.map
PYTHONPATH=src python3 -m ot_fmg validate outputs/open_targets_states.map
```

To render strong disease-disease colocalisations as a sparse road network,
point the command at either one link file or the directory containing its
partitions. The defaults require at least 25,000 colocalisations and cap the
map at 250 roads:

```bash
PYTHONPATH=src python3 -m ot_fmg build-states-json \
  --states-json /path/to/states_additional.json.gz \
  --colocalisations /path/to/disease.coloc.json.gz \
  --open-targets-features \
  --out outputs/open_targets_coloc.map
```

Use `--min-colocalisations` and `--max-routes` to override those conservative
defaults. Reverse-direction duplicates collapse to one road using the highest
`colocalisationCount`.

The build command also writes `outputs/open_targets.manifest.json`, mapping source disease ids to generated Azgaar ids.

By default the generated save keeps expensive visual layers sparse, matching native Azgaar saves more closely: `pack.cells` contains the full cell data, but visible cell outline paths, state fills, province fills, and halo filters are not serialized into the SVG preview unless explicitly enabled. Use `--render-cells-layer` only for debugging the generated Voronoi cells.

## Inputs

The converter can read `.csv`, `.json`, `.jsonl`, and `.parquet` files, including
gzip-compressed JSON/JSONL partitions. Link inputs may also be directories.
Parquet requires `pandas` plus a parquet engine such as `pyarrow`.

See `examples/open_targets_map.example.yml` for the general multi-table config shape and
`examples/states_json.example.yml` for the direct flat state/province/leaf shape.
