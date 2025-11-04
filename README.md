# MLMD-BOM

**Proof of Concept:** Generate CycloneDX BOMs (modelboms and databoms) from ML Metadata (MLMD) with live interactive visualization.

MLMD is a library for recording and retrieving metadata associated with machine learning workflows. It helps track artifacts, executions, and lineage information, enabling reproducibility and traceability in ML pipelines.  

For more information, see the official [ML Metadata repository](https://github.com/google/ml-metadata).

To fully realize secure and trustworthy AI workflows, this project is designed for tight integration with Kubeflow, an open-source machine learning platform built on Kubernetes. Leveraging Kubeflow’s native MLMD tracking, every step—from data ingestion to model deployment—is captured in the MLMD store (if the metadata service is enabled and properly configured). This repository extracts that metadata and generates verifiable, tamper-resistant AI Bill of Materials (AIBOMs) for pipelines provided by ML engineers. This approach provides end-to-end traceability and integrity, making it possible to audit and trust the complete lineage of AI assets.

For more information, see the official [KubeFlow documentation](https://www.kubeflow.org/docs/).

> **Disclaimer:** Tamper resistance, security and verifiability and full Kubeflow integration are not yet implemented. This project is a proof of concept and these features are planned for future development.

## What you get

- MLMD database with multiple pipelines, models, datasets, dependencies
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

## 1. Docker Compose Simulation

### Prerequisites

- Docker
- Docker Compose

### Setup env files

Two env files live in `./env` and are loaded by Docker Compose.

- `env/default.env` (used by populator and app)
  - LOG_LEVEL=INFO, LOG_FORMAT=plain
  - MLMD_SQLITE_PATH=/mlmd-sqlite/mlmd.db
  - MLMD_HOST=mysql, MLMD_PORT=3306, MLMD_DATABASE=mlmd, MLMD_USER=mlmd, MLMD_PASSWORD=mlmdpass, MLMD_ROOT_PASSWORD=rootpass
  - SCENARIO_YAML=scenarios/complex-scenario-2.yaml
  - MLMD_RESET_DB=yes
  - EXTRACT_CONTEXT= (optional)

- `env/mysql.env` (used by the MySQL container in the MySQL compose file)
  - MYSQL_DATABASE=mlmd
  - MYSQL_USER=mlmd
  - MYSQL_PASSWORD=mlmdpass
  - MYSQL_ROOT_PASSWORD=rootpass

Notes

- You don’t need to set `MLMD_BACKEND` in these files: the compose files set it per service (`sqlite` in `docker-compose.yml`, `mysql` in `docker-compose.mysql.yml`).
- Change `SCENARIO_YAML` to switch the simulated pipeline (see `populator/scenarios/*.yaml`). An example value is: `scenarios/complex-scenario-2.yaml`.
- `MLMD_RESET_DB=no` will likely break the generation because interfering data -> set it to 'yes'.
- `EXTRACT_CONTEXT` lets you focus on a specific MLMD context/pipeline when generating BOMs.

### 1.1 Database

There are two options for persistent storage: SQLite and MySQL.

SQLite (default in `docker-compose.yml`)

- Easiest to run locally; data is a single file under `./mlmd-sqlite/mlmd.db`.
- The env var `MLMD_SQLITE_PATH=/mlmd-sqlite/mlmd.db` is set in `env/default.env` and the host folder `./mlmd-sqlite` is mounted into both services.

MySQL (in `docker-compose.mysql.yml`)

- Starts a `mysql:8.0` container with a healthcheck and initializes the `mlmd` database.
- Credentials are provided via `env/mysql.env` (defaults: db `mlmd`, user `mlmd/mlmdpass`, root `rootpass`).
- The server is configured for `mysql_native_password` to match MLMD client expectations.
- Data volume is persisted in the named volume `mlmd_mysql_data`.

### 1.2 MLMD Populator

This is the service that simulates pipelines and experiments that are run in for example KubeFlow and populate the ml-metadata database.

Multiple scenarios are provided which can be loaded into the database.

What it does

- Starts with an empty MLMD store (optionally resets it) and loads a scenario from `populator/scenarios/*.yaml`.
- Supports both backends via `MLMD_BACKEND`:

  - `sqlite` (local file, default in `docker-compose.yml`)
  - `mysql` (external container, default in `docker-compose.mysql.yml`)

Key environment variables (from `env/default.env`)

- SCENARIO_YAML: Path to the scenario YAML to load (default: `scenarios/complex-scenario-2.yaml`).
- MLMD_RESET_DB: `yes|no` whether to reset the MLMD DB before populating (default: `yes`).
- LOG_LEVEL / LOG_FORMAT: tweak logging (`INFO` and `plain` by default).

Outputs and logs

- Writes logs to `./logs/mlmd-populator.log` (mounted into the container).
- Populates the MLMD store; no files are written by the populator itself.

### 1.3 MLMD App

This is the actual service that should be integrated in a real life KubeFlow setup. It reads from the ml-metadata database and generates BOM files accordingly. The Viewer is able to transform these BOMs in visual graphs (see [Section 2](#2-viewer-vite--react)).

What it does

- Connects to the same MLMD store as the populator (SQLite or MySQL).
- Extracts models and datasets (including lineage) and generates CycloneDX JSON files.
- Writes to `./output/`:

  - `output/cyclonedx/*.cyclonedx.json` — per model and per dataset
  - `output/extracted_mlmd*.json` — extracted raw metadata snapshots

Key environment variables (from `env/default.env`)

- EXTRACT_CONTEXT: Optional MLMD context/pipeline filter; leave empty to process everything.
- MLMD_* connection variables.
- LOG_LEVEL / LOG_FORMAT.

Outputs and logs

- Writes logs to `./logs/mlmd-app.log`.
- All artifacts are in `./output` and are consumed by the Viewer.

### Run everything together

Choose a backend and bring up the stack.

SQLite (2 services: populator → app)

```bash
docker compose -f docker-compose.yml up --build
```

MySQL (3 services: mysql → populator → app)

Note: You might have to run this twice, because the first time the healthcheck will not work and mysql will not be initialized in time.

```bash
docker compose -f docker-compose.mysql.yml up --build
```

What to expect

- The populator will run, populate MLMD, and exit successfully.
- The app will then connect, generate CycloneDX files into `./output/cyclonedx/`, and exit.
- Logs are written to `./logs/` (`mlmd-populator.log`, `mlmd-app.log`).

View the results

- Start the Viewer (see [Section 2](#2-viewer-vite--react)) to visualize the generated BOMs from `./output`.

### Run components separately with certain env

If the mysql is runnnig and we want to run certain containers again with different environment variables, this is also possible. See following examples:

Run the populator with a different scenario (while for example mysql is still running)

```bash
docker compose -f docker-compose.mysql.yml run -e SCENARIO_YAML=scenarios/simple-scenario-1.yaml mlmd-populator
```

Run the app again with different extraction context (while for example mysql is still running)

```bash
docker compose -f docker-compose.mysql.yml run -e EXTRACT_CONTEXT=tabular-pipeline mlmd-bom
```

These will work for the SQLite database too: use `-f docker-compose.yml`.

### Clean up containers

Keep volumes/data:

```bash
docker compose -f docker-compose.yml down
docker compose -f docker-compose.mysql.yml down
```

Also remove MySQL data volume:

```bash
docker compose -f docker-compose.mysql.yml down --volumes
```

Also remove images (destructive):

```bash
docker compose -f docker-compose.mysql.yml down --rmi all --volumes
```

Note: --volumes removes named volumes (data will be lost).

## 2. Viewer (Vite + React)

### Requirements

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
docker-compose.yml
docker-compose.mysql.yml
README.md
LICENSE
app/              # MLMD BOM generator (Python)
docs/             # Documentation and images
env/              # Environment variable files
logs/             # Log output
mlmd-sqlite/      # SQLite database storage
mysql-init/       # MySQL initialization scripts
output/           # Generated BOMs and extracted metadata
populator/        # MLMD database populator (Python)
scripts/          # Utility scripts
viewer/           # Interactive BOM viewer (Vite + React)
```

---

## License

See [LICENSE](LICENSE) for details.
