from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import logging

import yaml  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

from mlmd_support import (
    upsert_artifact_type,
    upsert_execution_type,
    upsert_context_type,
)
logger = logging.getLogger(__name__)


_PROP_TYPES = {
    "STRING": metadata_store_pb2.STRING,
    "INT": metadata_store_pb2.INT,
    "DOUBLE": metadata_store_pb2.DOUBLE,
}


def _coerce(value: Any, t: int) -> Any:
    """Coerce value to the MLMD scalar type t (STRING/INT/DOUBLE)."""
    if t == metadata_store_pb2.STRING:
        return "" if value is None else str(value)
    if t == metadata_store_pb2.INT:
        # Best-effort int conversion
        if isinstance(value, bool):  # avoid True->1 surprises; require explicit int
            return 1 if value else 0
        try:
            return int(value)
        except Exception:
            # Fallback: 0
            return 0
    if t == metadata_store_pb2.DOUBLE:
        try:
            return float(value)
        except Exception:
            return 0.0
    # Default to string
    return "" if value is None else str(value)


def _set_props_typed(dst_props, values: Dict[str, Any], type_map: Dict[str, int]) -> None:
    for k, v in (values or {}).items():
        pt = type_map.get(k, metadata_store_pb2.STRING)
        cv = _coerce(v, pt)
        if pt == metadata_store_pb2.INT:
            dst_props[k].int_value = int(cv)
        elif pt == metadata_store_pb2.DOUBLE:
            dst_props[k].double_value = float(cv)
        else:
            dst_props[k].string_value = str(cv)


def populate_mlmd_from_scenario(store, scenario_path: str | Path) -> Dict[str, Any]:
    """
    Populate the MLMD store from a YAML scenario file.

    Schema (high level):
    - types:
        artifact: { TypeName: {properties: {propName: STRING|INT|DOUBLE}} }
        execution: { TypeName: {properties: {...}} }
        context: { TypeName: {properties: {...}} }
    - contexts: { ctxKey: {type: TypeName, name: string, properties: {...}} }
    - artifacts: { artKey: {type: TypeName, uri: string, properties: {...}, contexts: [ctxKey, ...]} }
    - executions: { exeKey: {type: TypeName, properties: {...}, contexts: [ctxKey, ...]} }
    - events: [ {execution: exeKey, type: INPUT|OUTPUT, artifact: artKey} ]
    - attributions: [ {context: ctxKey, artifact: artKey} ]
    - associations: [ {context: ctxKey, execution: exeKey} ]
    """
    path = Path(scenario_path)
    logger.info("loading scenario", extra={"path": str(path)})
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    # Upsert types and capture declared property types for coercion
    art_type_props: Dict[str, Dict[str, int]] = {}
    exe_type_props: Dict[str, Dict[str, int]] = {}
    ctx_type_props: Dict[str, Dict[str, int]] = {}

    for tname, spec in (data.get("types", {}).get("artifact", {}) or {}).items():
        props = {k: _PROP_TYPES.get(v, metadata_store_pb2.STRING)
                 for k, v in (spec.get("properties") or {}).items()}
        art_type_props[tname] = props
        upsert_artifact_type(store, tname, properties=props)
    for tname, spec in (data.get("types", {}).get("execution", {}) or {}).items():
        props = {k: _PROP_TYPES.get(v, metadata_store_pb2.STRING)
                 for k, v in (spec.get("properties") or {}).items()}
        exe_type_props[tname] = props
        upsert_execution_type(store, tname, properties=props)
    for tname, spec in (data.get("types", {}).get("context", {}) or {}).items():
        props = {k: _PROP_TYPES.get(v, metadata_store_pb2.STRING)
                 for k, v in (spec.get("properties") or {}).items()}
        ctx_type_props[tname] = props
        upsert_context_type(store, tname, properties=props)
    logger.debug("types upserted", extra={"artifact_types": len(
        art_type_props), "execution_types": len(exe_type_props), "context_types": len(ctx_type_props)})

    # Create contexts
    ctx_index: Dict[str, metadata_store_pb2.Context] = {}
    if data.get("contexts"):
        for key, item in data["contexts"].items():
            ctx = metadata_store_pb2.Context()
            ctx.type = item.get("type")
            # Resolve type id
            ctx.type_id = store.get_context_type(item.get("type")).id
            ctx.name = item.get("name") or key
            _set_props_typed(ctx.properties, item.get("properties") or {
            }, ctx_type_props.get(item.get("type"), {}))
            [cid] = store.put_contexts([ctx])
            ctx.id = cid
            ctx_index[key] = ctx
    logger.info("contexts created", extra={"count": len(ctx_index)})

    # Create artifacts
    art_index: Dict[str, metadata_store_pb2.Artifact] = {}
    if data.get("artifacts"):
        to_put: List[metadata_store_pb2.Artifact] = []
        keys: List[str] = []
        for key, item in data["artifacts"].items():
            a = metadata_store_pb2.Artifact()
            a.type_id = store.get_artifact_type(item.get("type")).id
            a.uri = item.get("uri", "")
            _set_props_typed(a.properties, item.get("properties") or {
            }, art_type_props.get(item.get("type"), {}))
            to_put.append(a)
            keys.append(key)
        ids = store.put_artifacts(to_put)
        for a, k, i in zip(to_put, keys, ids):
            a.id = i
            art_index[k] = a
    logger.info("artifacts created", extra={"count": len(art_index)})

    # Create executions
    exe_index: Dict[str, metadata_store_pb2.Execution] = {}
    if data.get("executions"):
        to_put_e: List[metadata_store_pb2.Execution] = []
        keys_e: List[str] = []
        for key, item in data["executions"].items():
            e = metadata_store_pb2.Execution()
            e.type_id = store.get_execution_type(item.get("type")).id
            _set_props_typed(e.properties, item.get("properties") or {
            }, exe_type_props.get(item.get("type"), {}))
            to_put_e.append(e)
            keys_e.append(key)
        ids_e = store.put_executions(to_put_e)
        for e, k, i in zip(to_put_e, keys_e, ids_e):
            e.id = i
            exe_index[k] = e
    logger.info("executions created", extra={"count": len(exe_index)})

    # Attributions and associations
    atts: List[metadata_store_pb2.Attribution] = []
    assocs: List[metadata_store_pb2.Association] = []
    for a in (data.get("attributions") or []):
        at = metadata_store_pb2.Attribution()
        at.artifact_id = art_index[a["artifact"]].id
        at.context_id = ctx_index[a["context"]].id
        atts.append(at)
    for s in (data.get("associations") or []):
        asn = metadata_store_pb2.Association()
        asn.execution_id = exe_index[s["execution"]].id
        asn.context_id = ctx_index[s["context"]].id
        assocs.append(asn)
    if atts or assocs:
        store.put_attributions_and_associations(atts, assocs)
    logger.debug("linked attributions/associations",
                 extra={"attributions": len(atts), "associations": len(assocs)})

    # Events (execution IO)
    evts: List[metadata_store_pb2.Event] = []
    for ev in (data.get("events") or []):
        e = metadata_store_pb2.Event()
        e.execution_id = exe_index[ev["execution"]].id
        e.artifact_id = art_index[ev["artifact"]].id
        e.type = metadata_store_pb2.Event.OUTPUT if ev.get(
            "type", "OUTPUT").upper() == "OUTPUT" else metadata_store_pb2.Event.INPUT
        evts.append(e)
    if evts:
        store.put_events(evts)
    logger.info("events created", extra={"count": len(evts)})

    # Link per-entity contexts if declared inline (optional convenience)
    from ml_metadata.proto import metadata_store_pb2 as pb2  # type: ignore
    extra_atts: List[pb2.Attribution] = []
    extra_assocs: List[pb2.Association] = []
    for key, item in (data.get("artifacts") or {}).items():
        for ctx_key in item.get("contexts", []) or []:
            at = pb2.Attribution()
            at.artifact_id = art_index[key].id
            at.context_id = ctx_index[ctx_key].id
            extra_atts.append(at)
    for key, item in (data.get("executions") or {}).items():
        for ctx_key in item.get("contexts", []) or []:
            asn = pb2.Association()
            asn.execution_id = exe_index[key].id
            asn.context_id = ctx_index[ctx_key].id
            extra_assocs.append(asn)
    if extra_atts or extra_assocs:
        store.put_attributions_and_associations(extra_atts, extra_assocs)
    if extra_atts or extra_assocs:
        logger.debug("extra links added", extra={"extra_attributions": len(
            extra_atts), "extra_associations": len(extra_assocs)})

    result = {
        "contexts": ctx_index,
        "artifacts": art_index,
        "executions": exe_index,
    }
    logger.info("scenario loaded", extra={"contexts": len(
        ctx_index), "artifacts": len(art_index), "executions": len(exe_index)})
    return result
