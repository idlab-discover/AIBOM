from __future__ import annotations


from typing import Any, Dict, List, Optional, Set
import logging

from packageurl import PackageURL  # type: ignore

from cyclonedx.builder.this import this_component as cdx_lib_component  # type: ignore
from cyclonedx.model.bom import Bom  # type: ignore
from cyclonedx.model.component import Component, ComponentType  # type: ignore
from cyclonedx.model import ExternalReference, ExternalReferenceType  # type: ignore
from cyclonedx.model import XsUri, Property  # type: ignore
from cyclonedx.model.tool import Tool  # type: ignore
from cyclonedx.model.dependency import Dependency  # type: ignore
from cyclonedx.output import make_outputter  # type: ignore
from cyclonedx.schema import OutputFormat as CxOutputFormat, SchemaVersion as CxSchemaVersion  # type: ignore

logger = logging.getLogger(__name__)


# --- Modular BOM and relation functions ---

def create_model_bom(metadata: Dict[str, Any]) -> Bom:
    """Create a BOM for an AI model."""
    bom = Bom()
    model_component = Component(
        name=metadata.get("model_name", "model"),
        version=metadata.get("version"),
        type=ComponentType.APPLICATION,
        description=f"ML model using {metadata.get('framework', '')} ({metadata.get('format', '')})",
        bom_ref=metadata.get("uri"),
    )
    if Property is not None:
        for k, v in (metadata.get("properties") or {}).items():
            try:
                model_component.properties.add(
                    Property(name=f"ml:{k}", value=str(v)))
            except Exception:
                pass
    try:
        bom.metadata.component = model_component
    except Exception:
        pass
    bom.components.add(model_component)
    # Add dependencies (libraries)
    created_dep_components: List[Component] = []
    for dep in metadata.get("dependencies", []):
        purl_obj = None
        if dep.get("purl"):
            try:
                purl_obj = PackageURL.from_string(dep["purl"])
            except Exception:
                purl_obj = None
        c = Component(
            name=dep.get("name"),
            version=dep.get("version"),
            type=ComponentType.LIBRARY,
            bom_ref=dep.get("purl") or dep.get("uri"),
            purl=purl_obj,
        )
        if Property is not None:
            for k, v in (dep.get("properties") or {}).items():
                try:
                    c.properties.add(Property(name=f"ml:{k}", value=str(v)))
                except Exception:
                    pass
        bom.components.add(c)
        created_dep_components.append(c)
    # Produced artifacts (evaluation reports, images, etc.) as external references on model
    # Skipping produced artifacts as external references (EvaluationReport, ContainerImage, etc.)
    # Register the dependency graph: model depends on its listed components
    try:
        if created_dep_components:
            bom.register_dependency(model_component, created_dep_components)
    except Exception:
        pass
    # Tools metadata
    try:
        if cdx_lib_component:
            bom.metadata.tools.components.add(cdx_lib_component())
        bom.metadata.tools.components.add(Component(
            name='mlmd-to-bom',
            type=ComponentType.APPLICATION,
            version='0.1.0'
        ))
    except Exception:
        try:
            bom.metadata.tools.tools.add(
                Tool(vendor="mlmd-bom", name="mlmd-to-bom", version="0.1.0"))
        except Exception:
            pass
    logger.debug("created model BOM", extra={"model": metadata.get(
        "model_name"), "version": metadata.get("version"), "deps": len(metadata.get("dependencies", []))})
    return bom


def add_model_lineage_relation(parent_bom: Bom, child_bom: Bom) -> None:
    """Add bidirectional lineage references between parent and child model BOMs.

    This function finds the model (application) component in each BOM and:
    - Adds an externalReference of type BOM on the child pointing to the parent's bom-ref
    - Adds an externalReference of type BOM on the parent pointing to the child's bom-ref
    Note: URLs are stored as URNs with the target bom-ref to avoid needing file paths or serials.
    """
    def find_model_component(b: Bom):
        comp = None
        try:
            # Prefer metadata.component if set
            comp = getattr(b.metadata, 'component', None)
        except Exception:
            comp = None
        if comp and getattr(comp, 'type', None) == ComponentType.APPLICATION:
            return comp
        for c in b.components:
            if getattr(c, 'type', None) == ComponentType.APPLICATION:
                return c
        return None

    parent_comp = find_model_component(parent_bom)
    child_comp = find_model_component(child_bom)
    if not parent_comp or not child_comp:
        logger.warning("could not locate model components for lineage", extra={
                       "has_parent": bool(parent_comp), "has_child": bool(child_comp)})
        return

    parent_ref = getattr(parent_comp, 'bom_ref', None)
    child_ref = getattr(child_comp, 'bom_ref', None)
    if not parent_ref or not child_ref:
        logger.warning("missing bom-ref for lineage",
                       extra={"parent_ref": bool(parent_ref), "child_ref": bool(child_ref)})
        return

    try:
        # Use a stable URN with bom-ref, viewers can resolve as needed
        parent_urn = XsUri(
            f"urn:mlmd-bom-ref:{parent_ref}") if XsUri else f"urn:mlmd-bom-ref:{parent_ref}"
        child_urn = XsUri(
            f"urn:mlmd-bom-ref:{child_ref}") if XsUri else f"urn:mlmd-bom-ref:{child_ref}"
        child_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=parent_urn,
                comment="Lineage: parent model BOM-ref",
            )
        )
        parent_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=child_urn,
                comment="Lineage: child model BOM-ref",
            )
        )
    except Exception:
        pass

    logger.debug("added bidirectional lineage", extra={
                 "parent_ref": str(parent_ref), "child_ref": str(child_ref)})


def add_model_dataset_relation(model_bom: Bom, dataset_bom: Bom) -> None:
    """
    Add relations between a model BOM and a dataset BOM (uses dataset). (both directions)
    - Adds externalReferences of type BOM on both components
    """
    def find_model_component(b: Bom):
        comp = None
        try:
            comp = getattr(b.metadata, 'component', None)
        except Exception:
            comp = None
        if comp and getattr(comp, 'type', None) == ComponentType.APPLICATION:
            return comp
        for c in b.components:
            if getattr(c, 'type', None) == ComponentType.APPLICATION:
                return c
        return None

    def find_dataset_component(b: Bom):
        data_type = getattr(ComponentType, 'DATA', None)
        comp = None
        try:
            comp = getattr(b.metadata, 'component', None)
        except Exception:
            comp = None
        if comp and getattr(comp, 'type', None) in (data_type, ComponentType.FILE):
            return comp
        for c in b.components:
            if getattr(c, 'type', None) in (data_type, ComponentType.FILE):
                return c
        return None

    model_comp = find_model_component(model_bom)
    dataset_comp = find_dataset_component(dataset_bom)
    if not model_comp or not dataset_comp:
        logger.warning("could not locate model/dataset components for relation", extra={
                       "has_model": bool(model_comp), "has_dataset": bool(dataset_comp)})
        return

    model_ref = getattr(model_comp, 'bom_ref', None)
    dataset_ref = getattr(dataset_comp, 'bom_ref', None)
    if not model_ref or not dataset_ref:
        logger.warning("missing bom-ref for model/dataset relation", extra={
                       "model_ref": bool(model_ref), "dataset_ref": bool(dataset_ref)})
        return

    try:
        ds_urn = XsUri(
            f"urn:mlmd-bom-ref:{dataset_ref}") if XsUri else f"urn:mlmd-bom-ref:{dataset_ref}"
        model_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=ds_urn,
                comment="Uses dataset BOM-ref",
            )
        )
        mdl_urn = XsUri(
            f"urn:mlmd-bom-ref:{model_ref}") if XsUri else f"urn:mlmd-bom-ref:{model_ref}"
        dataset_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=mdl_urn,
                comment="Used by model BOM-ref",
            )
        )
    except Exception:
        pass


def create_dataset_bom(metadata: Dict[str, Any]) -> Bom:
    """Create a BOM for a dataset."""
    bom = Bom()
    data_type = getattr(ComponentType, 'DATA', None) or ComponentType.FILE
    dataset_component = Component(
        name=metadata.get("dataset_name") or metadata.get("name") or "dataset",
        version=metadata.get("version"),
        type=data_type,
        description=f"Dataset {metadata.get('dataset_name') or metadata.get('name')}",
        bom_ref=metadata.get("uri"),
    )
    if Property is not None:
        for k, v in (metadata.get("properties") or {}).items():
            try:
                dataset_component.properties.add(
                    Property(name=f"ml:{k}", value=str(v)))
            except Exception:
                pass
    try:
        bom.metadata.component = dataset_component
    except Exception:
        pass
    bom.components.add(dataset_component)

    # Tools metadata
    try:
        if cdx_lib_component:
            bom.metadata.tools.components.add(cdx_lib_component())
        bom.metadata.tools.components.add(Component(
            name='mlmd-to-bom',
            type=ComponentType.APPLICATION,
            version='0.1.0'
        ))
    except Exception:
        try:
            bom.metadata.tools.tools.add(
                Tool(vendor="mlmd-bom", name="mlmd-to-bom", version="0.1.0"))
        except Exception:
            pass
    logger.debug("created dataset BOM", extra={"dataset": metadata.get(
        "dataset_name"), "version": metadata.get("version")})
    return bom


def add_dataset_lineage_relation(parent_bom: Bom, child_bom: Bom):
    """Add a parent/child dataset relations to a dataset BOM."""
    def find_dataset_component(b: Bom):
        data_type = getattr(ComponentType, 'DATA', None)
        comp = None
        try:
            comp = getattr(b.metadata, 'component', None)
        except Exception:
            comp = None
        if comp and getattr(comp, 'type', None) in (data_type, ComponentType.FILE):
            return comp
        for c in b.components:
            if getattr(c, 'type', None) in (data_type, ComponentType.FILE):
                return c
        return None

    parent_comp = find_dataset_component(parent_bom)
    child_comp = find_dataset_component(child_bom)
    if not parent_comp or not child_comp:
        logger.warning("could not locate dataset components for lineage", extra={
                       "has_parent": bool(parent_comp), "has_child": bool(child_comp)})
        return

    parent_ref = getattr(parent_comp, 'bom_ref', None)
    child_ref = getattr(child_comp, 'bom_ref', None)
    if not parent_ref or not child_ref:
        logger.warning("missing bom-ref for dataset lineage", extra={
                       "parent_ref": bool(parent_ref), "child_ref": bool(child_ref)})
        return

    try:
        parent_urn = XsUri(
            f"urn:mlmd-bom-ref:{parent_ref}") if XsUri else f"urn:mlmd-bom-ref:{parent_ref}"
        child_urn = XsUri(
            f"urn:mlmd-bom-ref:{child_ref}") if XsUri else f"urn:mlmd-bom-ref:{child_ref}"
        child_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=parent_urn,
                comment="Lineage: parent dataset BOM-ref",
            )
        )
        parent_comp.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=child_urn,
                comment="Lineage: child dataset BOM-ref",
            )
        )
    except Exception:
        pass

    logger.debug("added bidirectional dataset lineage", extra={
                 "parent_ref": str(parent_ref), "child_ref": str(child_ref)})


def write_cyclonedx_files(
    bom: Bom,
    out_json: Optional[str] = None,
    out_xml: Optional[str] = None
) -> None:
    """
    Write CycloneDX BOM to JSON and/or XML if the corresponding path is provided.
    If out_json is given, write JSON. If out_xml is given, write XML. No output is written by default.
    """
    try:
        schema = CxSchemaVersion.V1_6  # prefer 1.6 when supported
    except Exception:  # pragma: no cover
        schema = CxSchemaVersion.V1_5
    if out_json:
        outter_json = make_outputter(
            bom=bom, output_format=CxOutputFormat.JSON, schema_version=schema)
        with open(out_json, "w", encoding="utf-8") as f:
            f.write(outter_json.output_as_string(indent=2))
        logger.info("wrote CycloneDX JSON", extra={"path": out_json})
    if out_xml:
        outter_xml = make_outputter(
            bom=bom, output_format=CxOutputFormat.XML, schema_version=schema)
        with open(out_xml, "w", encoding="utf-8") as f:
            f.write(outter_xml.output_as_string(indent=2))
        logger.debug("wrote CycloneDX XML", extra={"path": out_xml})
