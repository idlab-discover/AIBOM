from __future__ import annotations

from typing import Any, Dict, List

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore


def extract_model_and_deps(
    store: "metadata_store.MetadataStore", context_name: str = None, model_type: str = "Model"
) -> List[Dict[str, Any]]:
    """
    Extract all models (optionally filtered by context) and their dependencies.
    Returns a list of dicts with keys: model_name, version, framework, format, uri, dependencies[].
    """
    # Simple cache for type_id -> type_name to reduce RPCs
    type_name_cache: Dict[int, str] = {}

    def get_type_name_by_id(tid: int) -> str:
        if tid in type_name_cache:
            return type_name_cache[tid]
        types = store.get_artifact_types_by_id([tid])
        name = types[0].name if types else ""
        type_name_cache[tid] = name
        return name

    if context_name:
        # Filter by context
        ctxs = [c for c in store.get_contexts() if c.name == context_name]
        if not ctxs:
            raise RuntimeError(f"No context named {context_name}")
        ctx = ctxs[0]
        artifacts_in_ctx = store.get_artifacts_by_context(ctx.id)
        model_ids = [a.id for a in artifacts_in_ctx if get_type_name_by_id(a.type_id) == model_type]
        models = store.get_artifacts_by_id(model_ids)
    else:
        models = store.get_artifacts_by_type(model_type)
    if not models:
        raise RuntimeError(f"No {model_type} artifacts in MLMD store")

    def val(prop_map, key):
        v = prop_map.get(key)
        return getattr(v, "string_value", "") if v is not None else ""

    results = []
    for model in models:
        events_for_model = store.get_events_by_artifact_ids([model.id])
        exec_ids = {e.execution_id for e in events_for_model if e.type == metadata_store_pb2.Event.OUTPUT}
        deps: List["metadata_store_pb2.Artifact"] = []
        for ex_id in exec_ids:
            evts = store.get_events_by_execution_ids([ex_id])
            input_artifact_ids = [e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
            if input_artifact_ids:
                arts = store.get_artifacts_by_id(input_artifact_ids)
                # Filter out non-Library inputs if desired, but keep all for lineage
                deps.extend(arts)
        md = {
            "model_name": val(model.properties, "name") or "unknown",
            "version": val(model.properties, "version"),
            "framework": val(model.properties, "framework"),
            "format": val(model.properties, "format"),
            "uri": model.uri,
            "dependencies": [
                {
                    "name": val(a.properties, "name"),
                    "version": val(a.properties, "version"),
                    "purl": val(a.properties, "purl"),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                }
                for a in deps
            ],
        }
        results.append(md)
    return results


def get_models_by_property(store: "metadata_store.MetadataStore", key: str, value: str) -> List[Dict[str, Any]]:
    """Filter models by a typed property value and return their extracted metadata."""
    models = store.get_artifacts_by_type("Model")
    filtered = [m for m in models if getattr(m.properties.get(key, None), "string_value", None) == value]

    def val(prop_map, key):
        v = prop_map.get(key)
        return getattr(v, "string_value", "") if v is not None else ""

    # Cache for type resolution
    type_name_cache: Dict[int, str] = {}

    def get_type_name_by_id(tid: int) -> str:
        if tid in type_name_cache:
            return type_name_cache[tid]
        types = store.get_artifact_types_by_id([tid])
        name = types[0].name if types else ""
        type_name_cache[tid] = name
        return name

    results = []
    for model in filtered:
        events_for_model = store.get_events_by_artifact_ids([model.id])
        exec_ids = {e.execution_id for e in events_for_model if e.type == metadata_store_pb2.Event.OUTPUT}
        deps: List["metadata_store_pb2.Artifact"] = []
        for ex_id in exec_ids:
            evts = store.get_events_by_execution_ids([ex_id])
            input_artifact_ids = [e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
            if input_artifact_ids:
                arts = store.get_artifacts_by_id(input_artifact_ids)
                deps.extend(arts)
        md = {
            "model_name": val(model.properties, "name") or "unknown",
            "version": val(model.properties, "version"),
            "framework": val(model.properties, "framework"),
            "format": val(model.properties, "format"),
            "uri": model.uri,
            "dependencies": [
                {
                    "name": val(a.properties, "name"),
                    "version": val(a.properties, "version"),
                    "purl": val(a.properties, "purl"),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                }
                for a in deps
            ],
        }
        results.append(md)
    return results
