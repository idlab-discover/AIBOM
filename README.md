
# MLMD-BOM

**Proof of Concept:** Generate CycloneDX BOMs (modelboms and databoms) from ML Metadata (MLMD) with live interactive visualization.

MLMD is a library for recording and retrieving metadata associated with machine learning workflows. It helps track artifacts, executions, and lineage information, enabling reproducibility and traceability in ML pipelines.  

For more information, see the official ML Metadata repository: https://github.com/google/ml-metadata

This project is designed to integrate with Kubeflow, an open-source machine learning platform built on Kubernetes. In standard Kubeflow deployments, Kubeflow Pipelines records metadata in an MLMD (ML Metadata) store by default if the metadata service is enabled and properly configured. This repository can then be used to extract that metadata and build and sign AI Bill of Materials (AIBOMs) based on pipelines provided by ML Engineers.

For more information, see the official KubeFlow documentation: https://www.kubeflow.org/docs/

This would enable full AI lifecycle and lineage tracking.

---

## What you get

- In-memory MLMD with multiple pipelines, models, datasets, dependencies
- Extraction of model/dataset metadata with lineage and multi-pipeline relations
- Export to CycloneDX (per model and per dataset)
- Interactive viewer (Vite + React + vis-network)

Outputs are written to `output/`:

- `output/cyclonedx/` — per-model and per-dataset CycloneDX JSON
- `output/extracted_mlmd.json` — all
- `output/extracted_mlmd_models.json` — models only
- `output/extracted_mlmd_datasets.json` — datasets only
- `output/extracted_mlmd_multi.json` — multi-pipeline/combined

![MLMD-BOM live viewer screenshot](./docs/img/image.png)

---

## 1) Application (Generator)

### Requirements (Application)

- Docker
- Docker Compose

### Usage (Application)

Run the generator to produce BOMs into `output/` using Docker Compose.

Linux/macOS:

```bash
docker-compose up --build
```

Windows (PowerShell):

```powershell
docker-compose up --build
```

This will build and run the generator and write files under `output/`.

### Environment variables (Application)

You can control the generated data with these environment variables.

- SCENARIO_YAML — Path to a YAML file that defines the MLMD scenario. Default: `scenarios/demo-complex.yaml`.
- EXTRACT_CONTEXT — Filter which MLMD context to export (names come from the scenario). Examples: `expA`, `expB`, `demo-pipeline`.
- LOG_LEVEL — Python generator log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`).
- LOG_FORMAT — Python generator log format: `plain` (default) or `json`.

Linux/macOS (inline):

```bash
SCENARIO_YAML=scenarios/my-scenario.yaml EXTRACT_CONTEXT=expA docker-compose up --build
```

Windows (PowerShell):

```powershell
$env:SCENARIO_YAML="scenarios/my-scenario.yaml"
$env:EXTRACT_CONTEXT="expA"
docker-compose up --build
```

Windows (CMD):

```cmd
set SCENARIO_YAML=scenarios\my-scenario.yaml
set EXTRACT_CONTEXT=expA
docker-compose up --build
```

Logging examples (Linux/macOS):

```bash
# Linux/macOS
LOG_LEVEL=DEBUG docker-compose up --build

# JSON logs
LOG_FORMAT=json LOG_LEVEL=DEBUG docker-compose up --build
```

### Try these examples (Application)

- Default demo (no env vars): just run `docker-compose up --build` and then start the viewer.
- Use your own scenario: set `SCENARIO_YAML=scenarios/my-scenario.yaml`.
- Export a single context: set `EXTRACT_CONTEXT=expA`.
- Enable verbose logs: set `LOG_LEVEL=DEBUG`.

---

## 2) Viewer (Vite + React)

### Requirements (Viewer)

- Node.js (v18+ recommended)
- npm

### Usage (Viewer)

Start the viewer locally (reads from `../output/cyclonedx/`):

```bash
cd viewer
npm install
npm run dev
# Open http://localhost:5173
```

Features:

- Click a node to see CycloneDX JSON in the side panel; open full BOM files via links
- Double‑click a model or dataset node to open its full BOM in a new tab
- Drag nodes and toggle physics on/off
- Refresh button to re-read `output/cyclonedx` when files change

---

## Lineage and relationships

Each model and dataset is exported to its own BOM file (modelbom or databom). When multiple versions exist, a newer model links to its parent via BOM-Link; a single version will be emitted without lineage references.

- CycloneDX (specVersion 1.6):
  - Dependencies via the dependency graph
  - Lineage via `externalReferences` of type `bom` (BOM-Link URN)
  - Model–dataset relations via `externalReferences`

---

## Repository structure

```text
app/
  Dockerfile
  requirements.txt
  main.py
  mlmd_support.py
  extraction.py
  cyclonedx_gen.py
  spdx3_gen.py                    # currently not used
viewer/
  package.json
  vite.config.ts
  server/graphBuilder.ts          # graph builder used by dev server
  src/
    components/VisNetwork.tsx
    components/vis.css
    App.tsx
    main.tsx
  public/
viewer_old/                      # deprecated (no instructions)
output/
  cyclonedx/
  extracted_mlmd.json
  extracted_mlmd_models.json
  extracted_mlmd_datasets.json
  extracted_mlmd_multi.json
docker-compose.yml
```

---

## License

See [LICENSE](LICENSE) for details.
