from __future__ import annotations

from typing import Any, Dict, List
import logging

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

logger = logging.getLogger(__name__)


def connect_mlmd() -> "metadata_store.MetadataStore":
    cfg = metadata_store_pb2.ConnectionConfig()
    cfg.sqlite.SetInParent()
    store = metadata_store.MetadataStore(cfg)
    logger.info("connected to MLMD (sqlite in-memory)")
    return store


def upsert_artifact_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ArtifactType":
    # properties: dict of property name to type (e.g., metadata_store_pb2.STRING)
    at = metadata_store_pb2.ArtifactType(name=name)
    if properties:
        for k, v in properties.items():
            at.properties[k] = v
    at.id = store.put_artifact_type(at)
    logger.debug("upserted artifact type", extra={
                 "type": name, "properties": list((properties or {}).keys())})
    return at


def upsert_execution_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ExecutionType":
    et = metadata_store_pb2.ExecutionType(name=name)
    if properties:
        for k, v in properties.items():
            et.properties[k] = v
    et.id = store.put_execution_type(et)
    logger.debug("upserted execution type", extra={
                 "type": name, "properties": list((properties or {}).keys())})
    return et

    # Extraction logic moved to app/extraction.py

# --- Utility Functions ---


def upsert_context_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ContextType":
    ct = metadata_store_pb2.ContextType(name=name)
    if properties:
        for k, v in properties.items():
            ct.properties[k] = v
    ct.id = store.put_context_type(ct)
    logger.debug("upserted context type", extra={
                 "type": name, "properties": list((properties or {}).keys())})
    return ct


def get_context_by_name(store: "metadata_store.MetadataStore", type_name: str, context_name: str):
    ctx_type = store.get_context_type(type_name)
    ctxs = [c for c in store.get_contexts_by_type(
        type_name) if c.name == context_name]
    return ctxs[0] if ctxs else None


def get_artifact_by_name(store: "metadata_store.MetadataStore", type_name: str, artifact_name: str):
    return store.get_artifact_by_type_and_name(type_name, artifact_name)


def get_artifacts_by_uri(store: "metadata_store.MetadataStore", uri: str):
    return store.get_artifacts_by_uri(uri)

    # get_models_by_property moved to app/extraction.py
