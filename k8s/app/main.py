
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
from extraction import extract_model_deps_and_datasets
from cyclonedx_gen import (
    create_model_bom,
    add_model_lineage_relation,
    create_dataset_bom,
    add_dataset_lineage_relation,
    add_model_dataset_relation,
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


def safe_token(value: Any, default_token: str) -> str:
    """Return a sanitized token for filenames. If value is missing/empty after
    sanitization, use default_token. Prevents outputs like 'unknown-'."""
    try:
        raw = str(value) if value is not None else ""
    except Exception:
        raw = ""
    token = safe_filename(raw).strip("-").strip()
    if not token:
        token = safe_filename(default_token)
    return token


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
    prev_base = f"{safe(parent.get('model_name', 'model'))}-{safe_token(parent.get('version'), str(idx-1))}"
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
        # 1) Build BOMs for all versions first
        bom_cache: Dict[str, Any] = {}
        for idx, item in enumerate(items):
            model_name = item.get("model_name", "model")
            version = item.get("version") or f"{idx}"
            base = f"{safe_filename(model_name)}-{safe_token(version, str(idx))}"
            logger.debug("build model BOM", extra={
                "model": model_name, "version": version, "uri": item.get("uri")})
            bom_cache[base] = create_model_bom(item)

        # 2) Add lineage between adjacent versions
        for idx in range(1, len(items)):
            parent_item = items[idx - 1]
            child_item = items[idx]
            parent_base = f"{safe_filename(parent_item.get('model_name', 'model'))}-{safe_token(parent_item.get('version'), str(idx-1))}"
            child_base = f"{safe_filename(child_item.get('model_name', 'model'))}-{safe_token(child_item.get('version'), str(idx))}"
            parent_bom = bom_cache[parent_base]
            child_bom = bom_cache[child_base]
            logger.debug("link lineage (parent<->child)", extra={
                "parent": parent_item.get("uri"),
                "child": child_item.get("uri")
            })
            add_model_lineage_relation(parent_bom, child_bom)

        # 3) Write all BOMs once
        for idx, item in enumerate(items):
            model_name = item.get("model_name", "model")
            version = item.get("version") or f"{idx}"
            base = f"{safe_filename(model_name)}-{safe_token(version, str(idx))}"
            write_cyclonedx_files(
                bom_cache[base],
                out_json=str(cdx_dir / f"{base}.cyclonedx.json"),
            )


def group_datasets_by_name(dss: List[Dict[str, Any]]):
    by_name = {}
    for item in dss:
        by_name.setdefault(item.get("dataset_name", item.get(
            "name", "dataset")), []).append(item)
    return by_name


def emit_dataset_boms(by_name: Dict[str, List[Dict[str, Any]]], cdx_dir: Path):
    logger.debug("emit_dataset_boms", extra={"groups": len(by_name)})
    for name, items in by_name.items():
        logger.info("processing dataset group", extra={
                    "dataset": name, "versions": len(items)})
        items.sort(key=lambda x: version_key(x.get("version", "")))
        # Build all BOMs
        bom_cache: Dict[str, Any] = {}
        for idx, item in enumerate(items):
            ds_name = item.get("dataset_name") or item.get("name", "dataset")
            version = item.get("version") or f"{idx}"
            base = f"{safe_filename(ds_name)}-{safe_token(version, str(idx))}"
            logger.debug("build dataset BOM", extra={
                         "dataset": ds_name, "version": version, "uri": item.get("uri")})
            bom_cache[base] = create_dataset_bom(item)
        # Lineage between adjacent versions
        for idx in range(1, len(items)):
            parent_item = items[idx - 1]
            child_item = items[idx]
            parent_base = f"{safe_filename(parent_item.get('dataset_name') or parent_item.get('name', 'dataset'))}-{safe_token(parent_item.get('version'), str(idx-1))}"
            child_base = f"{safe_filename(child_item.get('dataset_name') or child_item.get('name', 'dataset'))}-{safe_token(child_item.get('version'), str(idx))}"
            add_dataset_lineage_relation(
                bom_cache[parent_base], bom_cache[child_base])
        # Write all BOMs
        for idx, item in enumerate(items):
            ds_name = item.get("dataset_name") or item.get("name", "dataset")
            version = item.get("version") or f"{idx}"
            base = f"{safe_filename(ds_name)}-{safe_token(version, str(idx))}"
            write_cyclonedx_files(
                bom_cache[base],
                out_json=str(cdx_dir / f"{base}.cyclonedx.json"),
            )


def emit_model_dataset_relations(models: List[Dict[str, Any]], datasets: List[Dict[str, Any]], cdx_dir: Path):
    """Create BOMs for models and datasets, wire lineage and model↔dataset relations, then write all once."""
    # Group and build caches
    models_by_name = group_models_by_name(models)
    datasets_by_name = group_datasets_by_name(datasets)

    # Build model BOMs (in memory, do not write yet)
    model_boms: Dict[str, Any] = {}
    for name, items in models_by_name.items():
        items.sort(key=lambda x: version_key(x.get("version", "")))
        for idx, item in enumerate(items):
            base = f"{safe_filename(item.get('model_name', 'model'))}-{safe_token(item.get('version'), str(idx))}"
            model_boms[base] = create_model_bom(item)

    # Build dataset BOMs (in memory, do not write yet)
    dataset_boms: Dict[str, Any] = {}
    uri_to_ds_key: Dict[str, str] = {}
    for name, items in datasets_by_name.items():
        items.sort(key=lambda x: version_key(x.get("version", "")))
        for idx, item in enumerate(items):
            ds_name = item.get("dataset_name") or item.get("name", "dataset")
            base = f"{safe_filename(ds_name)}-{safe_token(item.get('version'), str(idx))}"
            dataset_boms[base] = create_dataset_bom(item)
            uri = item.get("uri")
            if uri:
                uri_to_ds_key[uri] = base

    # Add model lineage (in memory)
    for name, items in models_by_name.items():
        for idx in range(1, len(items)):
            p = items[idx-1]
            c = items[idx]
            p_base = f"{safe_filename(p.get('model_name', 'model'))}-{safe_token(p.get('version'), str(idx-1))}"
            c_base = f"{safe_filename(c.get('model_name', 'model'))}-{safe_token(c.get('version'), str(idx))}"
            add_model_lineage_relation(model_boms[p_base], model_boms[c_base])

    # Add dataset lineage (in memory)
    for name, items in datasets_by_name.items():
        for idx in range(1, len(items)):
            p = items[idx-1]
            c = items[idx]
            p_base = f"{safe_filename(p.get('dataset_name') or p.get('name', 'dataset'))}-{safe_token(p.get('version'), str(idx-1))}"
            c_base = f"{safe_filename(c.get('dataset_name') or c.get('name', 'dataset'))}-{safe_token(c.get('version'), str(idx))}"
            add_dataset_lineage_relation(
                dataset_boms[p_base], dataset_boms[c_base])

    # Add model ↔ dataset relations (in memory)
    for name, items in models_by_name.items():
        for idx, m in enumerate(items):
            m_base = f"{safe_filename(m.get('model_name', 'model'))}-{safe_token(m.get('version'), str(idx))}"
            ds_uris = m.get("dataset_uris", []) or []
            for uri in ds_uris:
                key = uri_to_ds_key.get(uri)
                if not key:
                    continue
                add_model_dataset_relation(
                    model_boms[m_base], dataset_boms[key])

    # Now write all BOMs after all relationships are established
    for base, bom in model_boms.items():
        write_cyclonedx_files(bom, out_json=str(
            cdx_dir / f"{base}.cyclonedx.json"))
    for base, bom in dataset_boms.items():
        write_cyclonedx_files(bom, out_json=str(
            cdx_dir / f"{base}.cyclonedx.json"))


def main(argv: List[str]) -> int:
    setup_logging()
    t0 = time.time()
    out_dir = Path("output").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cdx_dir = out_dir / "cyclonedx"
    cdx_dir.mkdir(parents=True, exist_ok=True)

    # Connect to MLMD
    logger.info("connecting to MLMD store")
    store = connect_mlmd()

    # Extract model and dataset metadata
    context_name = os.environ.get("EXTRACT_CONTEXT")
    logger.info("extracting model and dataset metadata",
                extra={"context": context_name})
    extracted = extract_model_deps_and_datasets(
        store, context_name=context_name)
    models = extracted.get("models", [])
    datasets = extracted.get("datasets", [])
    md = models[0] if models else {}

    # Write extracted metadata
    write_json(md, out_dir / "extracted_mlmd.json")
    write_json(models, out_dir / "extracted_mlmd_models.json")
    write_json(datasets, out_dir / "extracted_mlmd_datasets.json")
    write_json(extracted, out_dir / "extracted_mlmd_multi.json")

    # Clean previous CycloneDX outputs
    clean_previous_outputs(cdx_dir, out_dir)

    # Group models by name
    by_name = group_models_by_name(models)
    logger.info("grouped models", extra={"groups": len(by_name)})

    # Emit per-model CycloneDX BOMs (this also handles lineage between versions)
    # New combined emission to also include datasets and relations
    emit_model_dataset_relations(models, datasets, cdx_dir)

    elapsed = time.time() - t0
    logger.info("generated CycloneDX BOMs", extra={
                "dir": str(cdx_dir), "elapsed_sec": round(elapsed, 3)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
