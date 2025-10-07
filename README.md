# MLMD-BOM

Proof of Concept: Generate CycloneDX and SPDX BOMs from ML Metadata (MLMD)

## Overview

This project demonstrates how to:
- Create an in-memory MLMD (ML Metadata) store with a fake model and dependencies.
- Extract model and dependency metadata.
- Export the metadata as CycloneDX and SPDX Bill of Materials (BOM) files.

Outputs are written to the `output/` directory.


## Requirements

- Docker
- Docker Compose

You do **not** need to install Python or any dependencies locally. Everything runs in containers.

## Usage

### Build and Run with Docker Compose

To build and run the project:

```bash
docker-compose up --build
```

This will:
- Build the Docker image
- Run the main script inside a container
- Write the following files to `output/` (in your project directory):
  - `extracted_mlmd.json`
  - `bom.cyclonedx.json`
  - `bom.cyclonedx.xml`
  - `bom.spdx.json`

You can change the output directory by setting the `OUTPUT_DIR` environment variable:

```bash
OUTPUT_DIR=some/other/dir docker-compose up --build
```


## Project Structure

```
app/
  main.py              # Main entry point
  mlmd_support.py      # MLMD utility functions
  cyclonedx_gen.py     # CycloneDX BOM generation
  spdx_gen.py          # SPDX BOM generation
output/                # Generated output files (mounted from container)
requirements.txt       # Python dependencies (used in Docker build)
Dockerfile             # Docker support
docker-compose.yml     # Docker Compose support
```

## License

See [LICENSE](LICENSE) for details.