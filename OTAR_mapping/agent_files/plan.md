# Open Targets to Azgaar Map Converter Plan

## Current Architecture

The converter is a small Python package under `src/ot_fmg`.

Main modules:

- `cli.py`: command line entry points
- `config.py`: defaults, YAML/JSON config loading, input path resolution
- `tables.py`: CSV, JSON, JSONL, and Parquet table loading
- `ontology.py`: deterministic primary path assignment for multi-parent DAGs
- `converter.py`: input normalization, layout, Azgaar pack construction, manifest writing
- `azgaar.py`: 46-section `.map` serialization, structural validation, SVG preview generation

## Implemented Flow

1. Load input data.
   - Config-driven mode reads separate disease, ontology, metrics, and optional link tables.
   - Direct mode reads flat `states.json` rows through `inputs.state_rows`.

2. Normalize flat state rows.
   - Deduplicate `leafId` values into disease rows.
   - Aggregate `populationSize` into `populationSize` max and `populationSizeTotal` sum.
   - Count memberships as `membershipCount`.
   - Generate ontology edges for root, state, province, and disease nodes.

3. Resolve primary ontology placement.
   - Assign top-level ancestor as state.
   - Assign second-level ancestor as province.
   - Assign each disease to one burg.
   - Preserve alternate direct parents in manifest metadata.

4. Generate map layout.
   - Create an all-land rectangular cell grid below the 100k-cell ceiling.
   - Allocate large state rectangles by disease count.
   - Allocate province rectangles within each state.
   - Pick unique cells for disease burgs inside their province region.

5. Build Azgaar pack data.
   - Generate `pack.states`, `pack.provinces`, `pack.burgs`, `pack.cells.*`, `grid`, and `pack.features`.
   - Keep cultures minimal and non-semantic.
   - Optionally generate capped disease-disease routes from a links table.

6. Serialize and validate.
   - Write 46 CRLF-delimited Azgaar save sections.
   - Write a companion manifest JSON.
   - Validate structural consistency with `ot-fmg validate`.

## Near-Term Plan

1. Finalize the `states.json` output path.
   - Regenerate the full map after the latest SVG outline-rendering fix.
   - Re-run structural validation.
   - Extract and render a fresh preview.

2. Smoke test in Azgaar.
   - Load the generated `.map` in the Fantasy Map Generator UI.
   - Check for critical loader errors.
   - Confirm states, provinces, burgs, and labels are visible.

3. Improve fantasy-map aesthetics without weakening Azgaar validity.
   - Replace rectangular treemap borders with more organic boundaries.
   - Keep `pack.cells.state` and `pack.cells.province` consistent with visual regions.
   - Keep SVG preview icon counts capped so 47k burgs do not visually black out the map.

4. Add schema and data diagnostics.
   - Report missing columns before build.
   - Report skipped malformed rows.
   - Report duplicate/multi-parent disease counts.
   - Report states/provinces that exist in source data but receive no primary burgs.

5. Add optional biological relationship routing.
   - Accept top disease-disease links from pre-aggregated Open Targets evidence.
   - Cap rendered routes by score.
   - Store omitted route counts in manifest metadata.

6. Package the CLI.
   - Expose `ot-fmg` as a console script from `pyproject.toml`.
   - Add install instructions for local editable use.
   - Keep the no-dependency CSV/JSON path working; document optional Parquet dependencies.

## Design Constraints

- Preserve Azgaar's containment model: state -> province -> burg.
- Do not overload cultures in v1.
- Stay below the 65,535 burg id ceiling.
- Stay below the configured grid cell ceiling.
- Keep source data traceability in the manifest.
- Avoid writing raw Open Targets edge volume into the map; aggregate first, render only selected links.

