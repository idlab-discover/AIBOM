from __future__ import annotations

from typing import Any, Dict, List

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore


def connect_mlmd() -> "metadata_store.MetadataStore":
    cfg = metadata_store_pb2.ConnectionConfig()
    cfg.sqlite.SetInParent()
    return metadata_store.MetadataStore(cfg)



def upsert_artifact_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ArtifactType":
    # properties: dict of property name to type (e.g., metadata_store_pb2.STRING)
    at = metadata_store_pb2.ArtifactType(name=name)
    if properties:
        for k, v in properties.items():
            at.properties[k] = v
    at.id = store.put_artifact_type(at)
    return at



def upsert_execution_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ExecutionType":
    et = metadata_store_pb2.ExecutionType(name=name)
    if properties:
        for k, v in properties.items():
            et.properties[k] = v
    et.id = store.put_execution_type(et)
    return et



def create_fake_mlmd(store: "metadata_store.MetadataStore") -> Dict[str, Any]:
    # Define explicit type properties
    model_type = upsert_artifact_type(store, "Model", properties={
        "name": metadata_store_pb2.STRING,
        "version": metadata_store_pb2.STRING,
        "framework": metadata_store_pb2.STRING,
        "format": metadata_store_pb2.STRING,
    })
    library_type = upsert_artifact_type(store, "Library", properties={
        "name": metadata_store_pb2.STRING,
        "version": metadata_store_pb2.STRING,
        "purl": metadata_store_pb2.STRING,
    })
    dataset_type = upsert_artifact_type(store, "Dataset", properties={
        "name": metadata_store_pb2.STRING,
        "split": metadata_store_pb2.STRING,
        "version": metadata_store_pb2.STRING,
    })
    run_type = upsert_execution_type(store, "TrainingRun", properties={
        "pipeline": metadata_store_pb2.STRING,
        "state": metadata_store_pb2.STRING,
        "run_id": metadata_store_pb2.STRING,
    })

    model = metadata_store_pb2.Artifact()
    model.type_id = model_type.id
    model.uri = "models://fakenet/1.0.0"
    model.properties["name"].string_value = "FakeNet"
    model.properties["version"].string_value = "1.0.0"
    model.properties["framework"].string_value = "TensorFlow"
    model.properties["format"].string_value = "SavedModel"

    deps = [
        {"name": "numpy", "version": "1.21.0", "purl": "pkg:pypi/numpy@1.21.0"},
        {"name": "tensorflow", "version": "2.6.0", "purl": "pkg:pypi/tensorflow@2.6.0"},
    ]
    dep_artifacts: List["metadata_store_pb2.Artifact"] = []
    for d in deps:
        a = metadata_store_pb2.Artifact()
        a.type_id = library_type.id
        a.uri = f"pkg://{d['name']}/{d['version']}"
        a.properties["name"].string_value = d["name"]
        a.properties["version"].string_value = d["version"]
        a.properties["purl"].string_value = d["purl"]
        dep_artifacts.append(a)

    [model_id] = store.put_artifacts([model])
    model.id = model_id
    dep_ids = store.put_artifacts(dep_artifacts)
    for a, i in zip(dep_artifacts, dep_ids):
        a.id = i

    # Create dataset artifact used for training
    dataset = metadata_store_pb2.Artifact()
    dataset.type_id = dataset_type.id
    dataset.uri = "data://demo-dataset/2025-10-01/train"
    dataset.properties["name"].string_value = "demo-dataset"
    dataset.properties["split"].string_value = "train"
    dataset.properties["version"].string_value = "2025-10-01"
    [dataset_id] = store.put_artifacts([dataset])
    dataset.id = dataset_id

    # First training run
    exe = metadata_store_pb2.Execution()
    exe.type_id = run_type.id
    exe.properties["pipeline"].string_value = "demo-pipeline"
    exe.properties["state"].string_value = "COMPLETED"
    exe.properties["run_id"].string_value = "run-001"
    [exe_id] = store.put_executions([exe])
    exe.id = exe_id

    # Context support: create contexts and link
    experiment_type = upsert_context_type(store, "Experiment", properties={"note": metadata_store_pb2.STRING})
    experiment = metadata_store_pb2.Context()
    experiment.type_id = experiment_type.id
    experiment.name = "exp1"
    experiment.properties["note"].string_value = "My first experiment."
    [experiment_id] = store.put_contexts([experiment])
    experiment.id = experiment_id

    pipeline_ctx_type = upsert_context_type(store, "Pipeline", properties={"owner": metadata_store_pb2.STRING})
    pipeline_ctx = metadata_store_pb2.Context()
    pipeline_ctx.type_id = pipeline_ctx_type.id
    pipeline_ctx.name = "demo-pipeline"
    pipeline_ctx.properties["owner"].string_value = "ml-team"
    [pipeline_ctx_id] = store.put_contexts([pipeline_ctx])
    pipeline_ctx.id = pipeline_ctx_id

    # Link model and execution to context
    from ml_metadata.proto import metadata_store_pb2 as pb2
    attribution = pb2.Attribution()
    attribution.artifact_id = model.id
    attribution.context_id = experiment.id
    association1 = pb2.Association()
    association1.execution_id = exe.id
    association1.context_id = experiment.id
    association2 = pb2.Association()
    association2.execution_id = exe.id
    association2.context_id = pipeline_ctx.id
    store.put_attributions_and_associations([attribution], [association1, association2])

    events = []
    e_out = metadata_store_pb2.Event()
    e_out.artifact_id = model.id
    e_out.execution_id = exe.id
    e_out.type = metadata_store_pb2.Event.OUTPUT
    events.append(e_out)
    # Inputs: libraries and dataset
    for a in dep_artifacts + [dataset]:
        e_in = metadata_store_pb2.Event()
        e_in.artifact_id = a.id
        e_in.execution_id = exe.id
        e_in.type = metadata_store_pb2.Event.INPUT
        events.append(e_in)
    store.put_events(events)

    # Second training run with updated dependencies and dataset -> produces model v1.1.0
    deps2 = [
        {"name": "numpy", "version": "1.22.0", "purl": "pkg:pypi/numpy@1.22.0"},
        {"name": "tensorflow", "version": "2.7.0", "purl": "pkg:pypi/tensorflow@2.7.0"},
        {"name": "pandas", "version": "1.3.5", "purl": "pkg:pypi/pandas@1.3.5"},
    ]
    dep2_artifacts: List["metadata_store_pb2.Artifact"] = []
    for d in deps2:
        a2 = metadata_store_pb2.Artifact()
        a2.type_id = library_type.id
        a2.uri = f"pkg://{d['name']}/{d['version']}"
        a2.properties["name"].string_value = d["name"]
        a2.properties["version"].string_value = d["version"]
        a2.properties["purl"].string_value = d["purl"]
        dep2_artifacts.append(a2)
    dep2_ids = store.put_artifacts(dep2_artifacts)
    for a2, i2 in zip(dep2_artifacts, dep2_ids):
        a2.id = i2

    dataset2 = metadata_store_pb2.Artifact()
    dataset2.type_id = dataset_type.id
    dataset2.uri = "data://demo-dataset/2025-10-02/train"
    dataset2.properties["name"].string_value = "demo-dataset"
    dataset2.properties["split"].string_value = "train"
    dataset2.properties["version"].string_value = "2025-10-02"
    [dataset2_id] = store.put_artifacts([dataset2])
    dataset2.id = dataset2_id

    model2 = metadata_store_pb2.Artifact()
    model2.type_id = model_type.id
    model2.uri = "models://fakenet/1.1.0"
    model2.properties["name"].string_value = "FakeNet"
    model2.properties["version"].string_value = "1.1.0"
    model2.properties["framework"].string_value = "TensorFlow"
    model2.properties["format"].string_value = "SavedModel"
    [model2_id] = store.put_artifacts([model2])
    model2.id = model2_id

    exe2 = metadata_store_pb2.Execution()
    exe2.type_id = run_type.id
    exe2.properties["pipeline"].string_value = "demo-pipeline"
    exe2.properties["state"].string_value = "COMPLETED"
    exe2.properties["run_id"].string_value = "run-002"
    [exe2_id] = store.put_executions([exe2])
    exe2.id = exe2_id

    # Additional experiment context
    experiment2 = metadata_store_pb2.Context()
    experiment2.type_id = experiment_type.id
    experiment2.name = "exp2"
    experiment2.properties["note"].string_value = "Second experiment."
    [experiment2_id] = store.put_contexts([experiment2])
    experiment2.id = experiment2_id

    # Link model2 and execution2 to contexts
    from ml_metadata.proto import metadata_store_pb2 as pb2
    attr2 = pb2.Attribution()
    attr2.artifact_id = model2.id
    attr2.context_id = experiment2.id
    assoc2a = pb2.Association()
    assoc2a.execution_id = exe2.id
    assoc2a.context_id = experiment2.id
    assoc2b = pb2.Association()
    assoc2b.execution_id = exe2.id
    assoc2b.context_id = pipeline_ctx.id
    store.put_attributions_and_associations([attr2], [assoc2a, assoc2b])

    events2 = []
    e2_out = metadata_store_pb2.Event()
    e2_out.artifact_id = model2.id
    e2_out.execution_id = exe2.id
    e2_out.type = metadata_store_pb2.Event.OUTPUT
    events2.append(e2_out)
    for a in dep2_artifacts + [dataset2]:
        e2_in = metadata_store_pb2.Event()
        e2_in.artifact_id = a.id
        e2_in.execution_id = exe2.id
        e2_in.type = metadata_store_pb2.Event.INPUT
        events2.append(e2_in)
    store.put_events(events2)

    return {
        "model": model,
        "deps": dep_artifacts,
        "dataset": dataset,
        "execution": exe,
        "contexts": {"experiment": experiment, "pipeline": pipeline_ctx},
        "model2": model2,
        "deps2": dep2_artifacts,
        "dataset2": dataset2,
        "execution2": exe2,
        "experiment2": experiment2,
        "models": [model, model2],
        "executions": [exe, exe2],
    }



    # Extraction logic moved to app/extraction.py

# --- Utility Functions ---

def upsert_context_type(store: "metadata_store.MetadataStore", name: str, properties: Dict[str, int] = None) -> "metadata_store_pb2.ContextType":
    ct = metadata_store_pb2.ContextType(name=name)
    if properties:
        for k, v in properties.items():
            ct.properties[k] = v
    ct.id = store.put_context_type(ct)
    return ct

def get_context_by_name(store: "metadata_store.MetadataStore", type_name: str, context_name: str):
    ctx_type = store.get_context_type(type_name)
    ctxs = [c for c in store.get_contexts_by_type(type_name) if c.name == context_name]
    return ctxs[0] if ctxs else None

def get_artifact_by_name(store: "metadata_store.MetadataStore", type_name: str, artifact_name: str):
    return store.get_artifact_by_type_and_name(type_name, artifact_name)

def get_artifacts_by_uri(store: "metadata_store.MetadataStore", uri: str):
    return store.get_artifacts_by_uri(uri)

    # get_models_by_property moved to app/extraction.py

