# MLMD-BOM

Proof of Concept: Generate CycloneDX and SPDX BOMs from ML Metadata (MLMD)

## Overview

This project demonstrates how to:
- Create an in-memory MLMD (ML Metadata) store with a fake model and dependencies.
- Extract model and dependency metadata.
- Export the metadata as Bill of Materials (BOM) files in CycloneDX and SPDX formats.

Outputs are written to `output/` with format-specific subfolders.

## Requirements

- Docker
- Docker Compose

You do not need to install Python or any dependencies locally. Everything runs in containers.

## Usage

### Build and run

```bash
docker-compose up --build
```

This will:
- Build the Docker image
- Run the main script inside a container
- Write files to `output/` (in your project directory), including:
  - `extracted_mlmd.json` and `extracted_mlmd_multi.json`
  - Per-model CycloneDX BOMs in `output/cyclonedx/`, e.g. `FakeNet-1.0.0.cyclonedx.json` and `.xml`
  - Per-model SPDX 3.0 BOMs in `output/spdx/`, e.g. `FakeNet-1.0.0.spdx3.json`

Optional environment variables:

- EXTRACT_CONTEXT: filter which MLMD context to export (default exports all fake contexts). Supports:
  - Experiment contexts: `exp1`, `exp2` (directly attributed model artifacts)
  - Pipeline context: `demo-pipeline` (models discovered via executions associated to the pipeline)

Examples:

```bash
# Export all (both versions) — includes lineage
docker-compose up --build

# Only the first experiment — emits a single-version BOM with no lineage
EXTRACT_CONTEXT=exp1 docker-compose up --build

# Only the second experiment — emits a single-version BOM with no lineage
EXTRACT_CONTEXT=exp2 docker-compose up --build

# Filter by pipeline context — finds models produced by that pipeline
EXTRACT_CONTEXT=demo-pipeline docker-compose up --build
```

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
  main.py              # Main entry point
  mlmd_support.py      # MLMD utility functions
  extraction.py        # Extract model + dependencies from MLMD
  cyclonedx_gen.py     # CycloneDX BOM generation (JSON + XML)
  spdx3_gen.py         # SPDX 3.0 JSON generation (per model)
  spdx_gen.py          # SPDX 2.3 generator (present, not used by default)
output/
  cyclonedx/           # Per-model CycloneDX BOMs
  spdx/                # Per-model SPDX 3.0 BOMs
requirements.txt       # Python dependencies (used in Docker build)
Dockerfile             # Docker support
docker-compose.yml     # Docker Compose support
```

## License

See [LICENSE](LICENSE) for details.