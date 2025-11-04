from __future__ import annotations

from typing import Any, Dict, List, Set, Iterable
import logging

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

logger = logging.getLogger(__name__)


def extract_model_deps_and_datasets(
    store: "metadata_store.MetadataStore",
    context_name: str | None = None,
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

    def _value_to_python(v) -> Any:
        """Decode an MLMD Value message to a python value using oneof discriminator."""
        if v is None:
            return ""
        try:
            which = v.WhichOneof("value")
        except Exception:
            which = None
        if which == "string_value":
            return getattr(v, "string_value", "")
        if which == "int_value":
            return getattr(v, "int_value", 0)
        if which == "double_value":
            return getattr(v, "double_value", 0.0)
        # Fallback heuristics if WhichOneof is unavailable
        if hasattr(v, "string_value") and getattr(v, "string_value", None) not in (None, ""):
            return v.string_value
        if hasattr(v, "int_value"):
            return v.int_value
        if hasattr(v, "double_value"):
            return v.double_value
        return ""

    def val_both(artifact: "metadata_store_pb2.Artifact", key: str) -> Any:
        """Get a property value by key from properties or custom_properties (properties win)."""
        # properties first
        v = artifact.properties.get(key)
        if v is not None:
            return _value_to_python(v)
        # then custom_properties
        try:
            cv = artifact.custom_properties.get(key)
        except Exception:
            cv = None
        if cv is not None:
            return _value_to_python(cv)
        return ""

    def val_any(artifact: "metadata_store_pb2.Artifact", keys: List[str]) -> Any:
        """Try multiple keys across properties and custom_properties and return first non-empty value."""
        for k in keys:
            v = val_both(artifact, k)
            if v not in (None, ""):
                return v
        return ""

    def all_props_both(artifact: "metadata_store_pb2.Artifact") -> Dict[str, Any]:
        """Merge typed and custom properties to a simple dict; typed properties take precedence."""
        out: Dict[str, Any] = {}
        # typed first
        for k, v in getattr(artifact, "properties", {}).items():
            out[k] = _value_to_python(v)
        # then custom for missing keys
        try:
            cprops = artifact.custom_properties
        except Exception:
            cprops = {}
        for k, v in getattr(cprops, "items", lambda: [])():
            if k not in out:
                out[k] = _value_to_python(v)
        return out

    def _available_artifact_type_names() -> List[str]:
        try:
            ats = store.get_artifact_types()
            return [t.name for t in ats]
        except Exception as e:
            logger.debug("failed to list artifact types",
                         extra={"err": str(e)})
            return []

    def _resolve_type_name_candidates(target: str, available: Iterable[str]) -> List[str]:
        """
        Resolve concrete MLMD artifact type names present in the store for a logical target like
        "Model" or "Dataset". Handles KFP v2 system.* types and common synonyms.
        Returns a non-empty list of type names to use, ordered by preference.
        """
        avail = list(available)
        lower_avail = {a.lower(): a for a in avail}

        # Exact match (case-sensitive or insensitive)
        if target in avail:
            return [target]
        if target.lower() in lower_avail:
            return [lower_avail[target.lower()]]

        # Known synonyms by logical target
        synonyms: Dict[str, List[str]] = {
            "Model": [
                "system.Model",
                "KerasModel",
                "PytorchModel",
                "TensorFlowSavedModel",
                "MLModel",
                "ModelArtifact",
            ],
            "Dataset": [
                "system.Dataset",
                "Example",
                "Examples",
                "MLTable",
            ],
        }
        cands: List[str] = []
        for s in synonyms.get(target, []):
            if s in avail:
                cands.append(s)
            elif s.lower() in lower_avail:
                cands.append(lower_avail[s.lower()])

        # Heuristic: anything that endswith or contains the token (case-insensitive)
        token = target.lower()
        for a in avail:
            al = a.lower()
            if al == token:
                continue
            if al.endswith(token) or token in al:
                if a not in cands:
                    cands.append(a)

        return cands

    def _collect_by_type_names(type_names: List[str]) -> List["metadata_store_pb2.Artifact"]:
        arts: List["metadata_store_pb2.Artifact"] = []
        for tn in type_names:
            try:
                arts.extend(store.get_artifacts_by_type(tn))
            except Exception as e:
                logger.debug("get_artifacts_by_type failed",
                             extra={"type": tn, "err": str(e)})
        return arts

    # --- Extract models ---
    available_types = _available_artifact_type_names()
    resolved_model_type_names = _resolve_type_name_candidates(
        "Model" if model_type == "Model" else model_type, available_types)
    resolved_dataset_type_names = _resolve_type_name_candidates(
        "Dataset" if dataset_type == "Dataset" else dataset_type, available_types)
    if not resolved_model_type_names:
        logger.warning(
            "no matching artifact type names found for models",
            extra={"requested": model_type, "available": available_types},
        )
    if not resolved_dataset_type_names:
        logger.warning(
            "no matching artifact type names found for datasets",
            extra={"requested": dataset_type, "available": available_types},
        )

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
            if get_type_name_by_id(a.type_id) in set(resolved_model_type_names) or get_type_name_by_id(a.type_id) == model_type
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
                    if get_type_name_by_id(a.type_id) in set(resolved_model_type_names) or get_type_name_by_id(a.type_id) == model_type
                ]
                models = store.get_artifacts_by_id(
                    model_ids2) if model_ids2 else []
    else:
        models = _collect_by_type_names(
            [model_type] + resolved_model_type_names)
    if not models:
        logger.error(
            "no models in metadata store",
            extra={
                "requested_model_type": model_type,
                "resolved_model_types": resolved_model_type_names,
                "context": context_name,
                "available_types": available_types,
            },
        )
        raise RuntimeError(
            f"No {model_type if model_type else 'Model'}-like artifacts in MLMD store"
        )

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
                    if get_type_name_by_id(a.type_id) in set(resolved_dataset_type_names) or get_type_name_by_id(a.type_id) == dataset_type:
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
                    if (get_type_name_by_id(a.type_id) in set(resolved_dataset_type_names) or get_type_name_by_id(a.type_id) == dataset_type) and a.uri:
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
            # Prefer canonical 'name', then common alternates from KFP/Kubeflow like 'display_name'
            "model_name": val_any(model, ["name", "model_name", "display_name"]) or "unknown",
            "version": val_any(model, ["version", "model_version", "version_name"]),
            "framework": val_any(model, ["framework", "ml_framework", "framework_name"]),
            "format": val_any(model, ["format", "model_format"]),
            "uri": model.uri,
            "properties": {k: v for k, v in all_props_both(model).items() if k not in ("name", "version", "framework", "format")},
            "dependencies": [
                {
                    "name": val_any(a, ["name", "display_name"]),
                    "version": val_any(a, ["version", "pkg_version"]),
                    "purl": val_any(a, ["purl", "package_url", "package-url"]),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                    "properties": {k: v for k, v in all_props_both(a).items() if k not in ("name", "version", "purl")},
                }
                for a in deps
            ],
            "dataset_uris": sorted(dataset_uri_set),
            "produced": [
                {
                    "name": val_any(a, ["name", "display_name"]),
                    "version": val_any(a, ["version", "artifact_version"]),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                    "properties": {k: v for k, v in all_props_both(a).items() if k not in ("name", "version")},
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
            if get_type_name_by_id(a.type_id) in set(resolved_dataset_type_names) or get_type_name_by_id(a.type_id) == dataset_type
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
                    if get_type_name_by_id(a.type_id) in set(resolved_dataset_type_names) or get_type_name_by_id(a.type_id) == dataset_type
                ]
                datasets = store.get_artifacts_by_id(
                    dataset_ids2) if dataset_ids2 else []
    else:
        datasets = _collect_by_type_names(
            [dataset_type] + resolved_dataset_type_names)
    dataset_results = []
    for ds in datasets:
        dataset_results.append({
            # Prefer 'name', then 'display_name'
            "dataset_name": val_any(ds, ["name", "dataset_name", "display_name"]) or "unknown",
            "version": val_any(ds, ["version", "dataset_version", "version_name"]),
            "uri": ds.uri,
            "properties": all_props_both(ds),
        })
    logger.info("extracted datasets", extra={
                "count": len(dataset_results), "context": context_name})

    return {"models": model_results, "datasets": dataset_results}


def get_models_by_property(store: "metadata_store.MetadataStore", key: str, value: str) -> List[Dict[str, Any]]:
    """Filter models by a typed property value and return their extracted metadata."""
    # Resolve model type names similar to the main extractor
    def _available_artifact_type_names() -> List[str]:
        try:
            ats = store.get_artifact_types()
            return [t.name for t in ats]
        except Exception:
            return []

    def _resolve_type_name_candidates(target: str, available: Iterable[str]) -> List[str]:
        avail = list(available)
        lower_avail = {a.lower(): a for a in avail}
        if target in avail:
            return [target]
        if target.lower() in lower_avail:
            return [lower_avail[target.lower()]]
        synonyms: Dict[str, List[str]] = {
            "Model": ["system.Model", "mlmd.Model", "KerasModel", "PytorchModel", "TensorFlowSavedModel", "MLModel", "ModelArtifact"],
        }
        cands: List[str] = []
        for s in synonyms.get(target, []):
            if s in avail:
                cands.append(s)
            elif s.lower() in lower_avail:
                cands.append(lower_avail[s.lower()])
        token = target.lower()
        for a in avail:
            al = a.lower()
            if al == token:
                continue
            if al.endswith(token) or token in al:
                if a not in cands:
                    cands.append(a)
        return cands

    def _collect_by_type_names(type_names: List[str]) -> List["metadata_store_pb2.Artifact"]:
        out: List["metadata_store_pb2.Artifact"] = []
        for tn in type_names:
            try:
                out.extend(store.get_artifacts_by_type(tn))
            except Exception:
                pass
        return out

    available_types = _available_artifact_type_names()
    resolved_model_type_names = _resolve_type_name_candidates(
        "Model", available_types)
    models = _collect_by_type_names(["Model"] + resolved_model_type_names)

    def _value_to_python(v) -> Any:
        try:
            which = v.WhichOneof("value")
        except Exception:
            which = None
        if which == "string_value":
            return getattr(v, "string_value", "")
        if which == "int_value":
            return getattr(v, "int_value", 0)
        if which == "double_value":
            return getattr(v, "double_value", 0.0)
        if hasattr(v, "string_value") and getattr(v, "string_value", None) not in (None, ""):
            return v.string_value
        if hasattr(v, "int_value"):
            return v.int_value
        if hasattr(v, "double_value"):
            return v.double_value
        return ""

    def _get_both(m: "metadata_store_pb2.Artifact", k: str) -> Any:
        v = m.properties.get(k)
        if v is not None:
            return _value_to_python(v)
        try:
            cv = m.custom_properties.get(k)
        except Exception:
            cv = None
        if cv is not None:
            return _value_to_python(cv)
        return ""

    filtered = [m for m in models if str(_get_both(m, key)) == str(value)]

    def val(m, key):
        return _get_both(m, key)

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
            "model_name": val(model, "name") or "unknown",
            "version": val(model, "version"),
            "framework": val(model, "framework"),
            "format": val(model, "format"),
            "uri": model.uri,
            "dependencies": [
                {
                    "name": val(a, "name"),
                    "version": val(a, "version"),
                    "purl": val(a, "purl"),
                    "uri": a.uri,
                    "type": get_type_name_by_id(a.type_id),
                }
                for a in deps
            ],
        }
        results.append(md)
    return results
