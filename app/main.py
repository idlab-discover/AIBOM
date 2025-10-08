#!/usr/bin/env python3
from __future__ import annotations

"""
PoC: Build fake MLMD metadata and export CycloneDX and SPDX BOMs.
- Creates an in-memory MLMD store with fake model/deps
- Writes outputs into ./output
"""

import json
import os
import sys
from pathlib import Path
from typing import List

from mlmd_support import connect_mlmd, create_fake_mlmd
from extraction import extract_model_and_deps
from cyclonedx_gen import create_cyclonedx_bom, write_cyclonedx_files
from spdx3_gen import create_spdx3_document


def write_metadata_snapshot(md, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(md, f, indent=2)


def main(argv: List[str]) -> int:

    # Output dir (fixed, no environment override)
    out_dir = Path("output").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cdx_dir = out_dir / "cyclonedx"
    spdx_dir = out_dir / "spdx"
    cdx_dir.mkdir(parents=True, exist_ok=True)
    spdx_dir.mkdir(parents=True, exist_ok=True)

    # Setup MLMD, create fake data, extract
    store = connect_mlmd()
    create_fake_mlmd(store)
    # Optional filtering by context via env var
    context_name = os.environ.get("EXTRACT_CONTEXT")
    mds = extract_model_and_deps(store, context_name=context_name)
    md = mds[0] if mds else {}

    # Write outputs
    write_metadata_snapshot(md, str(out_dir / "extracted_mlmd.json"))
    write_metadata_snapshot(mds, str(out_dir / "extracted_mlmd_multi.json"))

    # Generate per-model BOMs only. Combined BOMs are disabled.
    do_combined = False

    # Helper for safe filenames
    def safe(s: str) -> str:
        return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in s)

    # Sort models by semantic-ish version to establish lineage (fallback to lexical)
    def version_key(v: str) -> tuple:
        parts = []
        for p in (v or "").split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(p)
        return tuple(parts)

    # Group by model name for lineage chains
    by_name = {}
    for item in mds:
        by_name.setdefault(item.get("model_name", "model"), []).append(item)

    # Clean: remove previous BOM outputs to avoid stale content
    # Remove any previous CycloneDX files in new subfolder and legacy root
    for p in cdx_dir.glob("*.cyclonedx.*"):
        try:
            p.unlink()
        except Exception:
            pass
    for p in out_dir.glob("*.cyclonedx.*"):
        try:
            p.unlink()
        except Exception:
            pass
    # Remove any previous SPDX files in new subfolder and legacy root
    for p in spdx_dir.glob("*.spdx*.json"):
        try:
            p.unlink()
        except Exception:
            pass
    for p in out_dir.glob("*.spdx*.json"):
        try:
            p.unlink()
        except Exception:
            pass

    # Emit per-model BOMs

    # Emit per-model BOMs for all versions that participate in lineage
    for name, items in by_name.items():
        items.sort(key=lambda x: version_key(x.get("version", "")))
        if len(items) < 2:
            continue
        # Build a small index for child/parent lookups
        for idx, item in enumerate(items):
            model_name = item.get("model_name", "model")
            version = item.get("version", f"{idx}")
            base = f"{safe(model_name)}-{safe(version)}"

            parent = items[idx - 1] if idx > 0 else None
            child = items[idx + 1] if idx + 1 < len(items) else None

            # Gather BOM-Link identifiers from parent if available
            parent_bom_serial = None
            parent_bom_version = None
            parent_model_bom_ref = None
            parent_cx_url = None
            if parent is not None:
                prev_base = f"{safe(parent.get('model_name','model'))}-{safe(parent.get('version', str(idx-1)))}"
                parent_cx_url = str((cdx_dir / f"{prev_base}.cyclonedx.json").as_uri())
                prev_cx_path = cdx_dir / f"{prev_base}.cyclonedx.json"
                if prev_cx_path.exists():
                    try:
                        with open(prev_cx_path, "r", encoding="utf-8") as fh:
                            prev_bom = json.load(fh)
                        parent_bom_serial = prev_bom.get("serialNumber")
                        parent_bom_version = prev_bom.get("version", 1)
                        ref = None
                        meta = prev_bom.get("metadata", {})
                        comp = meta.get("component") or {}
                        ref = comp.get("bom-ref")
                        if not ref:
                            for c in prev_bom.get("components", []):
                                if c.get("type") == "application":
                                    ref = c.get("bom-ref")
                                    break
                        parent_model_bom_ref = ref
                    except Exception:
                        parent_bom_serial = None
                        parent_bom_version = None
                        parent_model_bom_ref = None

            # CycloneDX per-model (JSON + XML)
            bom = create_cyclonedx_bom(
                item,
                parent_bom_url=parent_cx_url,
                parent_bom_serial=parent_bom_serial,
                parent_bom_version=parent_bom_version if isinstance(parent_bom_version, int) else None,
                parent_model_bom_ref=parent_model_bom_ref,
            )
            write_cyclonedx_files(
                bom,
                out_json=str(cdx_dir / f"{base}.cyclonedx.json"),
                out_xml=str(cdx_dir / f"{base}.cyclonedx.xml"),
            )
            # Post-process CycloneDX JSON to ensure BOM-Link URN to parent and bump to 1.6
            cdx_path = cdx_dir / f"{base}.cyclonedx.json"
            try:
                with open(cdx_path, "r", encoding="utf-8") as fh:
                    cdx = json.load(fh)
                if parent_bom_serial and parent_model_bom_ref:
                    bom_link = f"urn:cdx:{parent_bom_serial}/{parent_bom_version or 1}#{parent_model_bom_ref}"
                    meta = cdx.setdefault("metadata", {})
                    comp = meta.setdefault("component", {})
                    extrefs = comp.setdefault("externalReferences", [])
                    if not any(er.get("type") == "bom" and er.get("url") == bom_link for er in extrefs):
                        extrefs.append({"type": "bom", "url": bom_link, "comment": "Parent/ancestor model via BOM-Link"})
                    model_bom_ref = comp.get("bom-ref")
                    if model_bom_ref:
                        for c in cdx.get("components", []):
                            if c.get("bom-ref") == model_bom_ref:
                                c.setdefault("externalReferences", [])
                                if not any(er.get("type") == "bom" and er.get("url") == bom_link for er in c["externalReferences"]):
                                    c["externalReferences"].append({"type": "bom", "url": bom_link, "comment": "Parent/ancestor model via BOM-Link"})
                                break
                cdx["specVersion"] = "1.6"
                cdx["$schema"] = "http://cyclonedx.org/schema/bom-1.6.schema.json"
                with open(cdx_path, "w", encoding="utf-8") as fh:
                    json.dump(cdx, fh, indent=4)
            except Exception:
                pass

            # SPDX 3.0 per-model: include lineage edge back to parent only (descendantOf)
            spdx3_obj = create_spdx3_document(
                item,
                document_name=f"{model_name}-{version}",
                document_version=1,
                parent_doc_name=(f"{parent.get('model_name','model')}-{parent.get('version','')}" if parent else None),
                parent_doc_version=1,
                # no child pointers to avoid forward refs
                child_doc_name=None,
                child_doc_version=1,
            )
            with open(spdx_dir / f"{base}.spdx3.json", "w", encoding="utf-8") as fh:
                json.dump(spdx3_obj, fh, indent=2)

    # Post-pass: ensure all per-model CycloneDX have BOM-Link URN to their immediate parent and specVersion 1.6
    for name, items in by_name.items():
        items.sort(key=lambda x: version_key(x.get("version", "")))
        for idx in range(1, len(items)):
            cur = items[idx]
            prev = items[idx - 1]
            cur_base = f"{safe(cur.get('model_name','model'))}-{safe(cur.get('version', str(idx)))}"
            prev_base = f"{safe(prev.get('model_name','model'))}-{safe(prev.get('version', str(idx-1)))}"
            cur_path = cdx_dir / f"{cur_base}.cyclonedx.json"
            prev_path = cdx_dir / f"{prev_base}.cyclonedx.json"
            try:
                with open(prev_path, "r", encoding="utf-8") as fh:
                    prev_bom = json.load(fh)
                parent_serial = prev_bom.get("serialNumber")
                parent_ver = prev_bom.get("version", 1)
                # Try to get parent model bom-ref
                parent_ref = None
                meta = prev_bom.get("metadata", {})
                comp = meta.get("component") or {}
                parent_ref = comp.get("bom-ref")
                if not parent_ref:
                    for c in prev_bom.get("components", []):
                        if c.get("type") == "application":
                            parent_ref = c.get("bom-ref")
                            break
                if not (parent_serial and parent_ref):
                    continue
                with open(cur_path, "r", encoding="utf-8") as fh:
                    cur_bom = json.load(fh)
                bom_link = f"urn:cdx:{parent_serial}/{parent_ver}#{parent_ref}"
                # Ensure metadata.component exists
                meta2 = cur_bom.setdefault("metadata", {})
                comp2 = meta2.setdefault("component", {})
                # Add externalReferences at both places
                for target in (comp2,):
                    ext = target.setdefault("externalReferences", [])
                    if not any(er.get("type") == "bom" and er.get("url") == bom_link for er in ext):
                        ext.append({"type": "bom", "url": bom_link, "comment": "Parent/ancestor model via BOM-Link"})
                # Also add to the actual component entry with matching bom-ref
                model_ref = comp2.get("bom-ref")
                if model_ref:
                    for c in cur_bom.get("components", []):
                        if c.get("bom-ref") == model_ref:
                            ext = c.setdefault("externalReferences", [])
                            if not any(er.get("type") == "bom" and er.get("url") == bom_link for er in ext):
                                ext.append({"type": "bom", "url": bom_link, "comment": "Parent/ancestor model via BOM-Link"})
                            break
                # Bump to 1.6 schema/spec
                cur_bom["specVersion"] = "1.6"
                cur_bom["$schema"] = "http://cyclonedx.org/schema/bom-1.6.schema.json"
                with open(cur_path, "w", encoding="utf-8") as fh:
                    json.dump(cur_bom, fh, indent=4)
            except Exception:
                continue

    # Combined BOMs disabled per request

    print("Generated in", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
