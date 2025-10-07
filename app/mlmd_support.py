from __future__ import annotations

from typing import Any, Dict, List

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore


def connect_mlmd() -> "metadata_store.MetadataStore":
    cfg = metadata_store_pb2.ConnectionConfig()
    cfg.sqlite.SetInParent()
    return metadata_store.MetadataStore(cfg)


def upsert_artifact_type(store: "metadata_store.MetadataStore", name: str) -> "metadata_store_pb2.ArtifactType":
    # Fresh in-memory store each run => directly create type
    at = metadata_store_pb2.ArtifactType(name=name)
    at.id = store.put_artifact_type(at)
    return at


def upsert_execution_type(store: "metadata_store.MetadataStore", name: str) -> "metadata_store_pb2.ExecutionType":
    et = metadata_store_pb2.ExecutionType(name=name)
    et.id = store.put_execution_type(et)
    return et


def create_fake_mlmd(store: "metadata_store.MetadataStore") -> Dict[str, Any]:
    model_type = upsert_artifact_type(store, "Model")
    library_type = upsert_artifact_type(store, "Library")
    run_type = upsert_execution_type(store, "TrainingRun")

    model = metadata_store_pb2.Artifact()
    model.type_id = model_type.id
    model.uri = "models://fakenet/1.0.0"
    model.custom_properties["name"].string_value = "FakeNet"
    model.custom_properties["version"].string_value = "1.0.0"
    model.custom_properties["framework"].string_value = "TensorFlow"
    model.custom_properties["format"].string_value = "SavedModel"

    deps = [
        {"name": "numpy", "version": "1.21.0", "purl": "pkg:pypi/numpy@1.21.0"},
        {"name": "tensorflow", "version": "2.6.0", "purl": "pkg:pypi/tensorflow@2.6.0"},
    ]
    dep_artifacts: List["metadata_store_pb2.Artifact"] = []
    for d in deps:
        a = metadata_store_pb2.Artifact()
        a.type_id = library_type.id
        a.uri = f"pkg://{d['name']}/{d['version']}"
        a.custom_properties["name"].string_value = d["name"]
        a.custom_properties["version"].string_value = d["version"]
        a.custom_properties["purl"].string_value = d["purl"]
        dep_artifacts.append(a)

    [model_id] = store.put_artifacts([model])
    model.id = model_id
    dep_ids = store.put_artifacts(dep_artifacts)
    for a, i in zip(dep_artifacts, dep_ids):
        a.id = i

    exe = metadata_store_pb2.Execution()
    exe.type_id = run_type.id
    exe.custom_properties["pipeline"].string_value = "demo-pipeline"
    [exe_id] = store.put_executions([exe])
    exe.id = exe_id

    events = []
    e_out = metadata_store_pb2.Event()
    e_out.artifact_id = model.id
    e_out.execution_id = exe.id
    e_out.type = metadata_store_pb2.Event.OUTPUT
    events.append(e_out)
    for a in dep_artifacts:
        e_in = metadata_store_pb2.Event()
        e_in.artifact_id = a.id
        e_in.execution_id = exe.id
        e_in.type = metadata_store_pb2.Event.INPUT
        events.append(e_in)
    store.put_events(events)

    return {"model": model, "deps": dep_artifacts, "execution": exe}


def extract_model_and_deps(store: "metadata_store.MetadataStore") -> Dict[str, Any]:
    all_models = store.get_artifacts_by_type("Model")
    if not all_models:
        raise RuntimeError("No Model artifacts in MLMD store")
    model = all_models[0]

    events_for_model = store.get_events_by_artifact_ids([model.id])
    exec_ids = {e.execution_id for e in events_for_model if e.type == metadata_store_pb2.Event.OUTPUT}
    deps: List["metadata_store_pb2.Artifact"] = []
    for ex_id in exec_ids:
        evts = store.get_events_by_execution_ids([ex_id])
        input_artifact_ids = [e.artifact_id for e in evts if e.type == metadata_store_pb2.Event.INPUT]
        if input_artifact_ids:
            arts = store.get_artifacts_by_id(input_artifact_ids)
            deps.extend(arts)

    def cp_val(cp_map, key):
        v = cp_map.get(key)
        return getattr(v, 'string_value', '') if v is not None else ''

    md = {
        "model_name": cp_val(model.custom_properties, "name") or "unknown",
        "version": cp_val(model.custom_properties, "version"),
        "framework": cp_val(model.custom_properties, "framework"),
        "format": cp_val(model.custom_properties, "format"),
        "uri": model.uri,
        "dependencies": [
            {
                "name": cp_val(a.custom_properties, "name"),
                "version": cp_val(a.custom_properties, "version"),
                "purl": cp_val(a.custom_properties, "purl"),
                "uri": a.uri,
            }
            for a in deps
        ],
    }
    return md

