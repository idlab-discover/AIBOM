mlmd-bom: MLMD -> CycloneDX/SPDX PoC
====================================

This is a proof-of-concept that uses the official ML Metadata (MLMD) library to create fake model metadata, extract model + dependency info, and generate both CycloneDX and SPDX BOMs.

What it does
------------
- Creates an in-memory MLMD store
- Inserts a Model artifact ("FakeNet" 1.0.0) and Library artifacts for numpy and tensorflow
- Links them via an Execution (inputs: libraries, output: model)
- Extracts the model and its dependencies from MLMD
- Emits:
	- CycloneDX JSON: `bom.cyclonedx.json`
	- CycloneDX XML: `bom.cyclonedx.xml`
	- SPDX JSON: `bom.spdx.json`
	- Extracted metadata snapshot: `extracted_mlmd.json`

Quick start
-----------

1) Create and activate a virtualenv (optional but recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Run the PoC (local will still run, but full MLMD mode is via Docker):

```bash
python3 main.py
```

You should see the BOM files created under the `output/` directory.

Use Docker to run with a Python version that supports MLMD:

```bash
docker build -t mlmd-bom .
docker run --rm -v "$PWD:/app" -w /app mlmd-bom
```

Using docker-compose:

```bash
docker compose up --build --abort-on-container-exit
```

Quick check inside container that MLMD is importable:

```bash
docker run --rm mlmd-bom python - <<'PY'
from ml_metadata.metadata_store import metadata_store
from ml_metadata.proto import metadata_store_pb2
print('MLMD OK:', metadata_store, metadata_store_pb2)
PY
```

Notes
-----
- MLMD is configured to use an in-memory SQLite DB, so nothing is persisted across runs.
- The model and dependency metadata are intentionally minimal for clarity.

Create a GitHub repo (main branch)
----------------------------------

```bash
git init
git add .
git commit -m "feat: MLMD -> CycloneDX/SPDX PoC"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

MLMD BOM Prototype
