# MLMD-BOM

**Proof of Concept:** Generate CycloneDX BOMs (modelboms and databoms) from ML Metadata (MLMD) with live interactive visualization.

MLMD is a library for recording and retrieving metadata associated with machine learning workflows. It helps track artifacts, executions, and lineage information, enabling reproducibility and traceability in ML pipelines.  

For more information, see the official [ML Metadata repository](https://github.com/google/ml-metadata).

To fully realize secure and trustworthy AI workflows, this project is designed for tight integration with Kubeflow, an open-source machine learning platform built on Kubernetes. Leveraging Kubeflow’s native MLMD tracking, every step—from data ingestion to model deployment—is captured in the MLMD store (if the metadata service is enabled and properly configured). This repository extracts that metadata and generates verifiable, tamper-resistant AI Bill of Materials (AIBOMs) for pipelines provided by ML engineers. This approach provides end-to-end traceability and integrity, making it possible to audit and trust the complete lineage of AI assets.

For more information, see the official [KubeFlow documentation](https://www.kubeflow.org/docs/).

> **Disclaimer:** Tamper resistance, security and verifiability and full Kubeflow integration are not yet implemented. This project is a proof of concept and these features are planned for future development.

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

```bash
docker-compose up --build
```

This will build and run the generator and write files under `output/`.

### Environment variables (Application)

You can control the generated data with these environment variables.

- SCENARIO_YAML — Path to a YAML file that defines the MLMD scenario. Default: `scenarios/complex-scenario-1.yaml`.
- EXTRACT_CONTEXT — Filter which MLMD context to export. A context is any named group (pipeline, run, experiment, or custom) defined in your scenario YAML. Only exact name matches are supported (e.g., `expA`, `expB`, `demo-pipeline`).
- LOG_LEVEL — Python generator log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`).
- LOG_FORMAT — Python generator log format: `plain` (default) or `json`.

### Scenarios and context

Scenario YAMLs are located in `app/scenarios/`:

- Simple scenarios (single pipeline):
  - `simple-scenario-1.yaml`
  - `simple-scenario-2.yaml`
  - `simple-scenario-3.yaml`
- Complex scenarios (multiple pipelines):
  - `complex-scenario-1.yaml`
  - `complex-scenario-2.yaml`
  - `complex-scenario-3.yaml`

You can use any of these by setting the `SCENARIO_YAML` environment variable.

Windows (PowerShell):

```powershell
$env:SCENARIO_YAML="scenarios/complex-scenario-2.yaml"; $env:EXTRACT_CONTEXT="expA"; 
docker-compose up --build
```

Windows (CMD):

```cmd
set SCENARIO_YAML=scenarios\complex-scenario-2.yaml &&
set EXTRACT_CONTEXT=expA &&
docker-compose up --build
```

Linux/macOS (Bash):

```bash
SCENARIO_YAML=scenarios/complex-scenario-2.yaml 
EXTRACT_CONTEXT=expA 
docker-compose up --build
```

### Change logging

Windows (PowerShell):

```powershell
$env:LOG_FORMAT="json"; $env:LOG_LEVEL="DEBUG"; 
docker-compose up --build
```

Windows (CMD):

```cmd
set LOG_FORMAT=json && set LOG_LEVEL=DEBUG && 
docker-compose up --build
```

Linux/macOS (Bash):

```bash
LOG_FORMAT=json LOG_LEVEL=DEBUG 
docker-compose up --build
```

---

## 2) Viewer (Vite + React)

### Requirements (Viewer)

- Node.js
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

Each model and dataset is exported to its own BOM file (modelbom or databom). When multiple versions exist, a newer model links to its parent via BOM-Link.

- CycloneDX (specVersion 1.6):
  - Dependencies via the dependency graph
  - Lineage via `externalReferences` of type `bom` (BOM-Link URN)
  - Model–dataset relations via `externalReferences`

---

## Repository structure

```bash
app/
  __init__.py
  cyclonedx_gen.py
  Dockerfile
  extraction.py
  main.py
  mlmd_support.py
  requirements.txt
  scenario_loader.py
  spdx3_gen.py                    # currently not used
  scenarios/
    simple-scenario-1.yaml
    simple-scenario-2.yaml
    simple-scenario-3.yaml
    complex-scenario-1.yaml
    complex-scenario-2.yaml
    complex-scenario-3.yaml
docs/
  img/
logs/
output/
  cyclonedx/
    # Generated BOMs
  # Extracted metadata JSONs
viewer/
  eslint.config.js
  index.html
  package.json
  README.md
  tsconfig.app.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts
  public/
  server/
    graphBuilder.ts
    logger.ts
  src/
    App.tsx
    index.css
    main.tsx
    assets/
    components/
      DetailsPanel.tsx
      HomePage.tsx
      NetworkGraph.tsx
    types/
      GraphData.tsx
docker-compose.yml
LICENSE
```

---

## License

See [LICENSE](LICENSE) for details.
