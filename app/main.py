#!/usr/bin/env python3
from __future__ import annotations

"""
PoC: Build fake MLMD metadata and export CycloneDX and SPDX BOMs.
- Creates an in-memory MLMD store with fake model/deps
- Writes outputs into ./output or $OUTPUT_DIR
"""

import json
import os
import sys
from pathlib import Path
from typing import List

from mlmd_support import connect_mlmd, create_fake_mlmd, extract_model_and_deps
from cyclonedx_gen import create_cyclonedx_bom, write_cyclonedx_files
from spdx_gen import create_spdx_document, write_spdx_json


def write_metadata_snapshot(md, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(md, f, indent=2)


def main(argv: List[str]) -> int:

    # Output dir
    out_dir = Path(os.environ.get("OUTPUT_DIR", "output")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Setup MLMD, create fake data, extract
    store = connect_mlmd()
    create_fake_mlmd(store)
    md = extract_model_and_deps(store)

    # Write outputs
    write_metadata_snapshot(md, str(out_dir / "extracted_mlmd.json"))

    # CycloneDX
    bom = create_cyclonedx_bom(md)
    write_cyclonedx_files(bom, out_json=str(out_dir / "bom.cyclonedx.json"), out_xml=str(out_dir / "bom.cyclonedx.xml"))

    # SPDX
    spdx_doc = create_spdx_document(md)
    write_spdx_json(spdx_doc, out_path=str(out_dir / "bom.spdx.json"))

    print("Generated in", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
