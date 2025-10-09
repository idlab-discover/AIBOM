
#!/usr/bin/env python3
from __future__ import annotations

"""
MLMD to CycloneDX BOM generator (SPDX deprecated).
Populates an in-memory MLMD store from a scenario file and writes CycloneDX outputs to ./output.
"""

import json
import os
import sys
import logging
import time
from pathlib import Path
from typing import List, Dict, Any

from mlmd_support import connect_mlmd
from scenario_loader import populate_mlmd_from_scenario
from extraction import extract_model_and_deps
from cyclonedx_gen import (
    create_model_bom,
    add_model_lineage_relation,
    write_cyclonedx_files,
)


logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure root logging from environment variables.

    LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
    LOG_FORMAT: 'plain' (default) or 'json' (lightweight JSON)
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt_choice = os.environ.get("LOG_FORMAT", "plain").lower()

    handler = logging.StreamHandler()
    if fmt_choice == "json":
        class JsonFormatter(logging.Formatter):
            # type: ignore[override]
            def format(self, record: logging.LogRecord) -> str:
                data = {
                    "ts": int(record.created * 1000),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                # Attach any "extra" fields added to the record
                std = {
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 'module', 'exc_info',
                    'exc_text', 'stack_info', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated', 'thread',
                    'threadName', 'processName', 'process', 'asctime'
                }
                for k, v in record.__dict__.items():
                    if k not in std and not k.startswith('_'):
                        try:
                            json.dumps({k: v})  # test serializable
                            data[k] = v
                        except Exception:
                            data[k] = str(v)
                if record.exc_info:
                    data["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(data)
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if called twice
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    else:
        # Replace existing handlers' formatter/level
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setLevel(level)
                h.setFormatter(handler.formatter)


def safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "-" for c in s)


def version_key(v: str) -> tuple:
    parts = []
    for p in (v or "").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(p)
    return tuple(parts)


def write_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.debug("wrote json", extra={"path": str(path)})


def clean_previous_outputs(cdx_dir: Path, out_dir: Path):
    removed = 0
    for p in cdx_dir.glob("*.cyclonedx.*"):
        try:
            p.unlink()
            removed += 1
        except Exception as e:
            logger.debug("failed to remove file", extra={
                         "path": str(p), "error": str(e)})
    for p in out_dir.glob("*.cyclonedx.*"):
        try:
            p.unlink()
            removed += 1
        except Exception as e:
            logger.debug("failed to remove file", extra={
                         "path": str(p), "error": str(e)})
    if removed:
        logger.info("cleaned previous cyclonedx outputs",
                    extra={"count": removed})


def group_models_by_name(mds: List[Dict[str, Any]]):
    by_name = {}
    for item in mds:
        by_name.setdefault(item.get("model_name", "model"), []).append(item)
    return by_name


def get_parent_bom_info(cdx_dir: Path, parent: Dict[str, Any], idx: int) -> tuple:
    safe = safe_filename
    prev_base = f"{safe(parent.get('model_name', 'model'))}-{safe(parent.get('version', str(idx-1)))}"
    parent_cx_url = str((cdx_dir / f"{prev_base}.cyclonedx.json").as_uri())
    prev_cx_path = cdx_dir / f"{prev_base}.cyclonedx.json"
    parent_bom_serial = None
    parent_bom_version = None
    parent_model_bom_ref = None
    if prev_cx_path.exists():
        try:
            with open(prev_cx_path, "r", encoding="utf-8") as fh:
                prev_bom = json.load(fh)
            parent_bom_serial = prev_bom.get("serialNumber")
            parent_bom_version = prev_bom.get("version", 1)
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
    return parent_cx_url, parent_bom_serial, parent_bom_version, parent_model_bom_ref


def emit_per_model_boms(by_name: Dict[str, List[Dict[str, Any]]], cdx_dir: Path):
    logger.debug("emit_per_model_boms", extra={"groups": len(by_name)})
    for name, items in by_name.items():
        logger.info("processing model group", extra={
                    "model": name, "versions": len(items)})
        items.sort(key=lambda x: version_key(x.get("version", "")))
        for idx, item in enumerate(items):
            model_name = item.get("model_name", "model")
            version = item.get("version", f"{idx}")
            base = f"{safe_filename(model_name)}-{safe_filename(version)}"
            parent = items[idx - 1] if idx > 0 else None
            parent_cx_url = None
            parent_bom_serial = None
            parent_bom_version = None
            parent_model_bom_ref = None
            logger.debug("model version", extra={
                         "model": model_name, "version": version, "uri": item.get("uri")})
            if parent is not None:
                parent_cx_url, parent_bom_serial, parent_bom_version, parent_model_bom_ref = get_parent_bom_info(
                    cdx_dir, parent, idx)
                logger.debug(
                    "parent bom info",
                    extra={
                        "parent_model": parent.get("model_name"),
                        "parent_version": parent.get("version"),
                        "cx_url": parent_cx_url,
                        "serial": parent_bom_serial,
                        "bom_version": parent_bom_version,
                        "parent_ref": parent_model_bom_ref,
                    },
                )
            # Create model BOM
            bom = create_model_bom(item)
            if parent_cx_url or (parent_bom_serial and parent_model_bom_ref):
                logger.debug("adding model lineage relation",
                             extra={"uri": item.get("uri")})
                add_model_lineage_relation(
                    bom,
                    model_bom_ref=item.get("uri"),
                    parent_bom_url=parent_cx_url,
                    parent_bom_serial=parent_bom_serial,
                    parent_bom_version=parent_bom_version if isinstance(
                        parent_bom_version, int) else None,
                    parent_model_bom_ref=parent_model_bom_ref,
                )
            write_cyclonedx_files(
                bom,
                out_json=str(cdx_dir / f"{base}.cyclonedx.json"),
            )


def main(argv: List[str]) -> int:
    setup_logging()
    t0 = time.time()
    out_dir = Path("output").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cdx_dir = out_dir / "cyclonedx"
    cdx_dir.mkdir(parents=True, exist_ok=True)

    # Connect and populate MLMD
    logger.info("connecting to MLMD store")
    store = connect_mlmd()
    scenario = os.environ.get(
        "SCENARIO_YAML", "app/scenarios/realistic-mlops.yaml")
    logger.info("populating MLMD from scenario", extra={"scenario": scenario})
    populate_mlmd_from_scenario(store, scenario)

    # Extract model metadata
    context_name = os.environ.get("EXTRACT_CONTEXT")
    logger.info("extracting model metadata", extra={"context": context_name})
    mds = extract_model_and_deps(store, context_name=context_name)
    md = mds[0] if mds else {}

    # Write extracted metadata
    write_json(md, out_dir / "extracted_mlmd.json")
    write_json(mds, out_dir / "extracted_mlmd_multi.json")

    # Clean previous CycloneDX outputs
    clean_previous_outputs(cdx_dir, out_dir)

    # Group models by name
    by_name = group_models_by_name(mds)
    logger.info("grouped models", extra={"groups": len(by_name)})

    # Emit per-model CycloneDX BOMs
    emit_per_model_boms(by_name, cdx_dir)

    elapsed = time.time() - t0
    logger.info("generated CycloneDX BOMs", extra={
                "dir": str(cdx_dir), "elapsed_sec": round(elapsed, 3)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
