from __future__ import annotations

from typing import Any, Dict, List, Set
import logging

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

logger = logging.getLogger(__name__)


def extract_model_deps_and_datasets(
    store: "metadata_store.MetadataStore",
    context_name: str = None,
    model_type: str = "Model",
    dataset_type: str = "Dataset",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract all models and datasets (optionally filtered by context).
    Returns a dict with keys: 'models', 'datasets'.
    Models do NOT include datasets as dependencies.

    Return structure:
    {
        "models": [<model1>, <model2>, ...], (List[Dict[str, Any]])
        "datasets": [<dataset1>, <dataset2>, ...] (List[Dict[str, Any]])
    }
    where each <model> (Dict[str, Any]) is a dict, e.g.,:
    {
        "model_name": str,
        "version": str,
        "framework": str,
        "format": str,
        "uri": str,
        "properties": {<other properties>},
        "dependencies": [
            {
                "name": str,
                "version": str,
                "purl": str,
                "uri": str,
                "type": str,
                "properties": {<other properties>}
            }, ...
        ],  
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

    def val(prop_map, key):
        v = prop_map.get(key)
        if v is None:
            return ""
        if hasattr(v, "string_value") and v.string_value:
            return v.string_value
        if hasattr(v, "int_value") and v.int_value:
            return str(v.int_value)
        if hasattr(v, "double_value") and v.double_value:
            return str(v.double_value)
        return ""

    def all_props(prop_map) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in prop_map.items():
            if hasattr(v, "string_value") and v.string_value:
                out[k] = v.string_value
            elif hasattr(v, "int_value") and v.int_value:
                out[k] = v.int_value
            elif hasattr(v, "double_value") and v.double_value:
                out[k] = v.double_value
        return out

    def is_type_match(type_name: str, target_short: str) -> bool:
        """Match either exact name or namespaced form like 'system.Model'."""
        if not type_name:
            return False
        return type_name == target_short or type_name.endswith(f".{target_short}")

    def get_types_matching(target_short: str) -> List[metadata_store_pb2.ArtifactType]:
        """Return all artifact types whose name equals target or ends with .target."""
        try:
            all_types = store.get_artifact_types()
        except Exception:
            all_types = []
        return [t for t in all_types if is_type_match(t.name, target_short)]

    # --- Extract models ---
    if context_name:
        ctxs = [c for c in store.get_contexts() if c.name == context_name]
        if not ctxs:
            logger.error("no context found", extra={"context": context_name})
            raise RuntimeError(f"No context named {context_name}")
        ctx = ctxs[0]
        artifacts_in_ctx = store.get_artifacts_by_context(ctx.id)
        model_ids = [
            a.id
            for a in artifacts_in_ctx
            if is_type_match(get_type_name_by_id(a.type_id), model_type)
        ]
        models = store.get_artifacts_by_id(model_ids) if model_ids else []
        # Fallback: executions in context
        if not models:
            execs_in_ctx = []
            try:
                execs_in_ctx = store.get_executions_by_context(ctx.id)
            except Exception:
                execs_in_ctx = []
            if execs_in_ctx:
                ex_ids = [e.id for e in execs_in_ctx]
                evts = store.get_events_by_execution_ids(ex_ids)
                out_artifact_ids = [
                    e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.OUTPUT]
                out_artifacts = store.get_artifacts_by_id(
                    out_artifact_ids) if out_artifact_ids else []
                model_ids2 = [
                    a.id
                    for a in out_artifacts
                    if is_type_match(get_type_name_by_id(a.type_id), model_type)
                ]
                models = store.get_artifacts_by_id(
                    model_ids2) if model_ids2 else []
    else:
        # union of all types matching the short name
        models = []
        matched_types = get_types_matching(model_type)
        logger.info(
            "model types matched",
            extra={"requested": model_type, "matched": [
                t.name for t in matched_types]},
        )
        for t in matched_types:
            try:
                models.extend(store.get_artifacts_by_type(t.name))
            except Exception:
                continue
    if not models:
        logger.error("no models in metadata store", extra={
                     "model_type": model_type, "context": context_name})
        raise RuntimeError(f"No {model_type} artifacts in MLMD store")

    model_results = []
    for model in models:
        events_for_model = store.get_events_by_artifact_ids([model.id])
        exec_ids_out: Set[int] = {
            e.execution_id for e in events_for_model if e.type == metadata_store_pb2.Event.OUTPUT}
        exec_ids_in: Set[int] = {
            e.execution_id for e in events_for_model if e.type == metadata_store_pb2.Event.INPUT}
        # Separate dataset and non-dataset dependencies
        deps: List["metadata_store_pb2.Artifact"] = []
        dataset_uri_set: Set[str] = set()
        for ex_id in exec_ids_out:
            evts = store.get_events_by_execution_ids([ex_id])
            input_artifact_ids = [
                e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
            if input_artifact_ids:
                arts = store.get_artifacts_by_id(input_artifact_ids)
                for a in arts:
                    if is_type_match(get_type_name_by_id(a.type_id), dataset_type):
                        if a.uri:
                            dataset_uri_set.add(a.uri)
                    else:
                        deps.append(a)
        produced: List["metadata_store_pb2.Artifact"] = []
        for ex_id in exec_ids_in:
            evts = store.get_events_by_execution_ids([ex_id])
            out_artifact_ids = [
                e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.OUTPUT]
            if out_artifact_ids:
                arts = store.get_artifacts_by_id(out_artifact_ids)
                produced.extend(arts)
            # Also include datasets that are INPUTs to executions where this model is an INPUT (e.g., Evaluation)
            in_artifact_ids = [
                e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
            if in_artifact_ids:
                in_arts = store.get_artifacts_by_id(in_artifact_ids)
                for a in in_arts:
                    if is_type_match(get_type_name_by_id(a.type_id), dataset_type) and a.uri:
                        dataset_uri_set.add(a.uri)
        logger.debug(
            "collected model relations",
            extra={
                "model_id": getattr(model, "id", None),
                "deps": len(deps),
                "datasets": len(dataset_uri_set),
                "produced": len(produced),
            },
        )
        md = {
            "model_name": val(model.properties, "name") or "unknown",
            "version": val(model.properties, "version"),
            "framework": val(model.properties, "framework"),
            "format": val(model.properties, "format"),
            "uri": model.uri,
            "properties": {k: v for k, v in all_props(model.properties).items() if k not in ("name", "version", "framework", "format")},
            "dependencies": [
                {
                    "name": val(a.properties, "name"),
                    "version": val(a.properties, "version"),
                    "purl": val(a.properties, "purl"),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                    "properties": {k: v for k, v in all_props(a.properties).items() if k not in ("name", "version", "purl")},
                }
                for a in deps
            ],
            "dataset_uris": sorted(dataset_uri_set),
            "produced": [
                {
                    "name": val(a.properties, "name"),
                    "version": val(a.properties, "version"),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                    "properties": {k: v for k, v in all_props(a.properties).items() if k not in ("name", "version")},
                }
                for a in produced
            ],
        }
        model_results.append(md)
    logger.info("extracted models", extra={
                "count": len(model_results), "context": context_name})

    # --- Extract datasets as top-level entities ---
    if context_name:
        ctxs = [c for c in store.get_contexts() if c.name == context_name]
        if not ctxs:
            logger.error("no context found", extra={"context": context_name})
            raise RuntimeError(f"No context named {context_name}")
        ctx = ctxs[0]
        artifacts_in_ctx = store.get_artifacts_by_context(ctx.id)
        dataset_ids = [
            a.id
            for a in artifacts_in_ctx
            if is_type_match(get_type_name_by_id(a.type_id), dataset_type)
        ]
        datasets = store.get_artifacts_by_id(
            dataset_ids) if dataset_ids else []
        # Fallback: executions in context
        if not datasets:
            execs_in_ctx = []
            try:
                execs_in_ctx = store.get_executions_by_context(ctx.id)
            except Exception:
                execs_in_ctx = []
            if execs_in_ctx:
                ex_ids = [e.id for e in execs_in_ctx]
                evts = store.get_events_by_execution_ids(ex_ids)
                out_artifact_ids = [
                    e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.OUTPUT]
                out_artifacts = store.get_artifacts_by_id(
                    out_artifact_ids) if out_artifact_ids else []
                dataset_ids2 = [
                    a.id
                    for a in out_artifacts
                    if is_type_match(get_type_name_by_id(a.type_id), dataset_type)
                ]
                datasets = store.get_artifacts_by_id(
                    dataset_ids2) if dataset_ids2 else []
    else:
        datasets = []
        matched_types = get_types_matching(dataset_type)
        logger.info(
            "dataset types matched",
            extra={"requested": dataset_type, "matched": [
                t.name for t in matched_types]},
        )
        for t in matched_types:
            try:
                datasets.extend(store.get_artifacts_by_type(t.name))
            except Exception:
                continue
    dataset_results = []
    for ds in datasets:
        dataset_results.append({
            "dataset_name": val(ds.properties, "name") or "unknown",
            "version": val(ds.properties, "version"),
            "uri": ds.uri,
            "properties": all_props(ds.properties),
        })
    logger.info("extracted datasets", extra={
                "count": len(dataset_results), "context": context_name})

    return {"models": model_results, "datasets": dataset_results}


def get_models_by_property(store: "metadata_store.MetadataStore", key: str, value: str) -> List[Dict[str, Any]]:
    """Filter models by a typed property value and return their extracted metadata."""
    def is_type_match(type_name: str, target_short: str) -> bool:
        return type_name == target_short or type_name.endswith(f".{target_short}")

    # Collect models across namespaced types
    models: List["metadata_store_pb2.Artifact"] = []
    try:
        types = store.get_artifact_types()
    except Exception:
        types = []
    model_type_names = [
        t.name for t in types if is_type_match(t.name, "Model")]
    for tn in model_type_names:
        try:
            models.extend(store.get_artifacts_by_type(tn))
        except Exception:
            continue
    filtered = [m for m in models if getattr(
        m.properties.get(key, None), "string_value", None) == value]

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
        exec_ids = {e.execution_id for e in events_for_model if e.type ==
                    metadata_store_pb2.Event.OUTPUT}
        deps: List["metadata_store_pb2.Artifact"] = []
        for ex_id in exec_ids:
            evts = store.get_events_by_execution_ids([ex_id])
            input_artifact_ids = [
                e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
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
