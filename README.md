# MLMD-BOM

Proof of Concept: Generate CycloneDX and SPDX BOMs from ML Metadata (MLMD)

## Overview

This project demonstrates how to:
- Create an in-memory MLMD (ML Metadata) store with a fake model and dependencies.
- Extract model and dependency metadata.
- Export the metadata as Bill of Materials (BOM) files in CycloneDX and SPDX formats.

Outputs are written to `output/` with format-specific subfolders.

An optional live HTML viewer is provided to visualize models, dependencies, and lineage. It runs as a small web app and auto-updates when new BOMs are written.

## Requirements

- Docker
- Docker Compose

You do not need to install Python or any dependencies locally. Everything runs in containers.

## Usage

### Build and run

```bash
docker compose up --build
```

This will:
- Build the generator image (`mlmd-bom`) and the viewer image (`bom-viewer`)
- Run the generator once to produce BOMs into `output/`
- Start a live viewer web app on http://localhost:8080
- Write files to `output/` (in your project directory), including:
  - `extracted_mlmd.json` and `extracted_mlmd_multi.json`
  - Per-model CycloneDX BOMs in `output/cyclonedx/`, e.g. `FakeNet-1.0.0.cyclonedx.json` and `.xml`
  - Per-model SPDX 3.0 BOMs in `output/spdx/`, e.g. `FakeNet-1.0.0.spdx3.json`

Environment variables:

- SCENARIO_YAML: path to a YAML file that defines the MLMD scenario to load. Defaults to `scenarios/demo-complex.yaml` bundled with the app.
- EXTRACT_CONTEXT: filter which MLMD context to export (uses names from your scenario). For the demo scenario, try:
  - Experiment contexts: `expA`, `expB`
  - Pipeline context: `demo-pipeline`

Examples:

Examples:
- Default (loads the bundled demo scenario): run the compose command above and open http://localhost:8080
- Export only one experiment from the demo scenario: set `EXTRACT_CONTEXT=expA` and re-run the generator service; the viewer will auto-refresh when new BOMs are written.
- Use your own scenario: set `SCENARIO_YAML=app/scenarios/my-scenario.yaml` and re-run the generator service.

### Visualize the BOMs (Live viewer)

- Open http://localhost:8080 for the combined view (CycloneDX + SPDX).
- Click a node to see its CycloneDX and SPDX JSON in the side panel; links let you open the full BOM files.
- Double‑click a model node to open its full BOM(s).
- Nodes are draggable; dependencies cluster around their model; shared dependencies appear between models; lineage edges are dashed orange.

The viewer watches `output/cyclonedx` and `output/spdx` and updates automatically when new files are created or existing files change.

## Lineage and relationships

Each model version is exported to its own BOM files, e.g. `FakeNet-1.0.0` and `FakeNet-1.1.0`. The newer version links to its immediate parent when both versions are present in the selection. If filtering results in a single version (e.g., `exp1` only), the BOM is emitted without lineage.

- CycloneDX (specVersion 1.6):
  - Dependencies are represented in the dependency graph.
  - Lineage is expressed via an externalReference of type `bom` on the model component using a BOM-Link URN pointing to the parent BOM.

- SPDX 3.0 JSON:
  - Dependencies are Packages with one `dependsOn` Relationship per dependency.
  - Lineage is a single `descendantOf` Relationship from the model to its parent model in the previous document.
  - `externalMaps` provides the cross-document mapping for that parent reference.

Why does SPDX show more relationships? SPDX models each edge explicitly (one Relationship per dependency and lineage link), whereas CycloneDX concentrates dependency information in a graph structure and puts lineage in external references, making it look more compact.

## Project structure

```
app/
  Dockerfile           # App container image
  requirements.txt     # App dependencies
  main.py              # Main entry point
  mlmd_support.py      # MLMD utility functions
  extraction.py        # Extract model + dependencies from MLMD
  cyclonedx_gen.py     # CycloneDX BOM generation (JSON + XML)
  spdx3_gen.py         # SPDX 3.0 JSON generation (per model)
  spdx_gen.py          # SPDX 2.3 generator (present, not used by default)
viewer/
  Dockerfile           # Viewer container image (Node)
  package.json         # Viewer web app dependencies and scripts
  server.js            # Live viewer server (Express + chokidar)
  build.js             # Static builder (kept for reference)
output/
  cyclonedx/           # Per-model CycloneDX BOMs
  spdx/                # Per-model SPDX 3.0 BOMs
docker-compose.yml     # Docker Compose orchestration
```

## License

See [LICENSE](LICENSE) for details.