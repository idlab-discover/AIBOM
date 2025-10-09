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


def add_model_lineage_relation(bom: Bom, model_bom_ref: str, parent_bom_url: Optional[str] = None, parent_bom_serial: Optional[str] = None, parent_bom_version: Optional[int] = None, parent_model_bom_ref: Optional[str] = None):
    """Add a parent/child model relation to a model BOM."""
    from cyclonedx.model.bom_ref import BomRef  # type: ignore
    # Convert model_bom_ref to BomRef if needed
    if not isinstance(model_bom_ref, BomRef):
        try:
            model_bom_ref_obj = BomRef(model_bom_ref)
        except Exception:
            model_bom_ref_obj = model_bom_ref
    else:
        model_bom_ref_obj = model_bom_ref

    model_component = None
    for c in bom.components:
        if getattr(c, 'bom_ref', None) == model_bom_ref_obj:
            logger.debug("found model component for lineage",
                         extra={"bom_ref": str(model_bom_ref)})
            model_component = c
            break

    if parent_bom_serial and parent_model_bom_ref:
        version_str = str(parent_bom_version or 1)
        # Avoid double 'urn:'
        serial = parent_bom_serial
        if serial.startswith('urn:'):
            serial = serial[len('urn:'):]
        bom_link = f"urn:cdx:{serial}/{version_str}#{parent_model_bom_ref}"
        url_val = XsUri(bom_link) if XsUri else bom_link
        model_component.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=url_val,
                comment="Parent/ancestor model via BOM-Link"
            )
        )

    elif parent_bom_url:
        url_val = XsUri(parent_bom_url) if XsUri else parent_bom_url
        model_component.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.BOM,
                url=url_val,
                comment="Parent/ancestor model BOM"
            )
        )
    logger.debug("added lineage reference", extra={"has_serial": bool(
        parent_bom_serial), "has_url": bool(parent_bom_url)})


def add_model_uses_dataset_relation(bom: Bom, model_bom_ref: str, dataset_bom_url: str):
    """Add a relation from a model to a dataset BOM (uses dataset)."""
    model_component = None
    for c in bom.components:
        if getattr(c, 'bom_ref', None) == model_bom_ref:
            model_component = c
            break
    if not model_component:
        return
    try:
        url_val = XsUri(dataset_bom_url) if XsUri else dataset_bom_url
        model_component.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.DATA,
                url=url_val,
                comment="Uses dataset BOM"
            )
        )
    except Exception:
        pass


def create_dataset_bom(metadata: Dict[str, Any]) -> Bom:
    """Create a BOM for a dataset."""
    bom = Bom()
    dataset_component = Component(
        name=metadata.get("dataset_name", "dataset"),
        version=metadata.get("version"),
        type=ComponentType.DATA,
        description=metadata.get("description", ""),
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
    return bom


def add_dataset_used_by_model(bom: Bom, dataset_bom_ref: str, model_bom_url: str):
    """Add a reference to a model BOM from a dataset BOM (used by model)."""
    dataset_component = None
    for c in bom.components:
        if getattr(c, 'bom_ref', None) == dataset_bom_ref:
            dataset_component = c
            break
    if not dataset_component:
        return
    try:
        url_val = XsUri(model_bom_url) if XsUri else model_bom_url
        dataset_component.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.APPLICATION,
                url=url_val,
                comment="Used by model BOM"
            )
        )
    except Exception:
        pass


def add_dataset_lineage_relation(bom: Bom, dataset_bom_ref: str, parent_bom_url: Optional[str] = None, parent_bom_serial: Optional[str] = None, parent_bom_version: Optional[int] = None, parent_dataset_bom_ref: Optional[str] = None):
    """Add a parent/child dataset relation to a dataset BOM."""
    dataset_component = None
    for c in bom.components:
        if getattr(c, 'bom_ref', None) == dataset_bom_ref:
            dataset_component = c
            break
    if not dataset_component:
        return
    if parent_bom_serial and parent_dataset_bom_ref:
        version_str = str(parent_bom_version or 1)
        bom_link = f"urn:cdx:{parent_bom_serial}/{version_str}#{parent_dataset_bom_ref}"
        try:
            url_val = XsUri(bom_link) if XsUri else bom_link
            dataset_component.external_references.add(
                ExternalReference(
                    type=ExternalReferenceType.BOM,
                    url=url_val,
                    comment="Parent/ancestor dataset via BOM-Link"
                )
            )
        except Exception:
            pass
    elif parent_bom_url:
        try:
            url_val = XsUri(parent_bom_url) if XsUri else parent_bom_url
            dataset_component.external_references.add(
                ExternalReference(
                    type=ExternalReferenceType.BOM,
                    url=url_val,
                    comment="Parent/ancestor dataset BOM"
                )
            )
        except Exception:
            pass
        try:
            if Property is not None:
                dataset_component.properties.add(
                    Property(name="lineage:parent-bom-url", value=parent_bom_url))
        except Exception:
            pass


def write_cyclonedx_files(
    bom: Bom,
    out_json: str = "bom.cyclonedx.json",
    out_xml: Optional[str] = "bom.cyclonedx.xml"
) -> None:
    # Prefer 1.6 when supported
    try:
        schema = CxSchemaVersion.V1_6  # prefer 1.6 when supported
    except Exception:  # pragma: no cover
        schema = CxSchemaVersion.V1_5
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
