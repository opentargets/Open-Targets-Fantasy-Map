# Open Targets to Azgaar Map Converter Tasks

## Done

- Built a Python package skeleton under `src/ot_fmg`.
- Added CLI commands:
  - `ot-fmg build`
  - `ot-fmg validate`
  - `ot-fmg build-states-json`
- Added table readers for:
  - CSV
  - JSON arrays
  - JSON objects with `rows` or `data`
  - newline-delimited JSON with `.json` or `.jsonl` suffix
  - Parquet, when pandas plus a parquet engine are installed
- Added deterministic ontology assignment for multi-parent DAGs.
- Added direct `states.json` ingestion:
  - `therapeuticArea` as state
  - `provinceId` as province
  - `leafId` as disease burg
  - `populationSize` as default metric input
- Added an artificial root for flat `states.json` rows so therapeutic areas remain states.
- Added manifest output with:
  - source state ids
  - source province ids
  - disease-to-burg mappings
  - primary path ids and names
  - alternate parent ids and names
- Added Azgaar `.map` serialization with 46 CRLF-delimited sections.
- Added structural validation for section count, JSON parseability, cell array lengths, burg cell occupancy, province-state references, and route shape.
- Added minimal non-semantic cultures:
  - `Wildlands`
  - `Diseases`
- Added example configs:
  - `examples/open_targets_map.example.yml`
  - `examples/states_json.example.yml`
- Added unit tests for:
  - map build and validation
  - JSON-lines `.json` fallback
  - flat state/province/leaf conversion
  - deterministic multi-parent ontology assignment
- Successfully built an initial full map from `/Users/alegbe/Downloads/states.json`:
  - 46,773 diseases
  - 26 states
  - 755 primary provinces
  - 63,144 cells
  - 0 routes
- Successfully validated the initial full map structurally.

## In Progress

- SVG preview polish for large maps.
  - The preview must avoid rendering all 46k burg icons as dense dark marks.
  - Outline-only SVG paths should use explicit transparent fill rather than `fill="none"` for renderer compatibility.

## Next

- Regenerate `outputs/open_targets_states.map` after the latest SVG outline fix.
- Re-run:

```bash
PYTHONPATH=src python3 -m ot_fmg validate outputs/open_targets_states.map
```

- Extract section 5 from the regenerated map into:

```text
outputs/open_targets_states_preview.svg
```

- Render or inspect the preview to confirm:
  - ocean background is visible
  - land is not blacked out
  - state regions are legible
  - province borders do not fill polygons
  - capped burg icons remain readable
- Load the regenerated map into Azgaar for a UI smoke test.
- Add a Playwright smoke test if the Azgaar UI can be run locally or opened against the hosted app.
- Add source-data diagnostics:
  - total input rows
  - unique therapeutic areas
  - unique provinces
  - unique leaves
  - duplicate leaf memberships
  - skipped rows
  - provinces/states without primary burgs
- Add config validation with clear errors for missing columns.
- Decide whether `populationSizeTotal`, `populationSize`, or another derived metric should drive visual prominence.
- Add optional input for top disease-disease links and route them with score caps.
- Add performance tests for synthetic 47k and near-ceiling 65k burg datasets.
- Package the CLI as a console script so the command can be run as `ot-fmg` after installation.

## Open Questions

- Should duplicate leaf memberships be represented only in the manifest, or should the visual map hint at multi-membership somehow?
- Should `therapeuticAreaName` labels be cleaned or shortened for map display?
- Should provinces with no primary disease after deterministic assignment remain visible as empty provinces, or should they be omitted as they are now?
- Which Open Targets metric should become the main fantasy-map visual signal for v1?
- Should routes represent disease-disease similarity, shared targets, shared credible sets, or another pre-aggregated biological relationship?

