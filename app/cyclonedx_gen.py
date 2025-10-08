from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# CycloneDX model imports (v11+ preferred with fallbacks)
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
try:  # v11+
    from cyclonedx.model.external_reference import ExternalReference, ExternalReferenceType  # type: ignore
except Exception:  # older libs
    try:
        from cyclonedx.model import ExternalReference, ExternalReferenceType  # type: ignore
    except Exception:
        ExternalReference = None  # type: ignore
        ExternalReferenceType = None  # type: ignore
try:
    from cyclonedx.model import XsUri  # type: ignore
except Exception:
    XsUri = None  # type: ignore
try:  # optional property support
    from cyclonedx.model import Property  # type: ignore
except Exception:  # pragma: no cover
    Property = None  # type: ignore
from cyclonedx.model.tool import Tool
try:
    from cyclonedx.model.dependency import Dependency
except Exception:  # pragma: no cover
    Dependency = None  # type: ignore

# Output helpers in latest lib
from cyclonedx.output import make_outputter
try:
    from cyclonedx.schema import OutputFormat as CxOutputFormat, SchemaVersion as CxSchemaVersion  # type: ignore
except Exception:
    # fallback for older libs
    from cyclonedx.output import OutputFormat as CxOutputFormat, SchemaVersion as CxSchemaVersion  # type: ignore

from packageurl import PackageURL
try:
    # Include the library's own component as a tool descriptor
    from cyclonedx.builder.this import this_component as cdx_lib_component  # type: ignore
except Exception:  # pragma: no cover
    cdx_lib_component = None  # type: ignore


def create_cyclonedx_bom(metadata: Dict[str, Any], parent_bom_url: Optional[str] = None, parent_bom_serial: Optional[str] = None, parent_bom_version: Optional[int] = None, parent_model_bom_ref: Optional[str] = None) -> Bom:
    bom = Bom()
    model_component = Component(
        name=metadata.get("model_name", "model"),
        version=metadata.get("version"),
        type=ComponentType.APPLICATION,
        description=f"ML model using {metadata.get('framework','')} ({metadata.get('format','')})",
        bom_ref=metadata.get("uri"),
    )
    # Add extra model properties if supported
    if Property is not None:
        for k, v in (metadata.get("properties") or {}).items():
            try:
                model_component.properties.add(Property(name=f"ml:{k}", value=str(v)))
            except Exception:
                pass

    # If a parent BOM URL or BOM-Link info is provided, add an external reference to indicate lineage
    if parent_bom_serial and parent_model_bom_ref:
        # Use CycloneDX BOM-Link URN: urn:cdx:<serial>/<version>#<bom-ref>
        version_str = str(parent_bom_version or 1)
        bom_link = f"urn:cdx:{parent_bom_serial}/{version_str}#{parent_model_bom_ref}"
        try:
            url_val = XsUri(bom_link) if XsUri else bom_link
            model_component.external_references.add(
                ExternalReference(
                    reference_type=ExternalReferenceType.BOM,  # type: ignore[arg-type]
                    url=url_val,  # type: ignore[arg-type]
                    comment="Parent/ancestor model via BOM-Link"
                )
            )
        except Exception:
            pass
    elif parent_bom_url:
        try:
            url_val = XsUri(parent_bom_url) if XsUri else parent_bom_url
            model_component.external_references.add(
                ExternalReference(
                    reference_type=ExternalReferenceType.BOM,  # type: ignore[arg-type]
                    url=url_val,  # type: ignore[arg-type]
                    comment="Parent/ancestor model BOM"
                )
            )
        except Exception:
            # Best-effort: if library version mismatch, ignore linking
            pass
        # Also add as a property for broader tool compatibility
        try:
            if Property is not None:
                model_component.properties.add(Property(name="lineage:parent-bom-url", value=parent_bom_url))
        except Exception:
            pass
    # Set as primary component so externalReferences appear under metadata.component
    try:
        bom.metadata.component = model_component
    except Exception:
        pass
    bom.components.add(model_component)

    created_dep_components: List[Component] = []

    for dep in metadata.get("dependencies", []):
        purl_obj = None
        if dep.get("purl"):
            try:
                purl_obj = PackageURL.from_string(dep["purl"])  # type: ignore[arg-type]
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
    try:
        for prod in metadata.get("produced", []) or []:
            label = prod.get("type") or "Produced"
            url = prod.get("uri") or prod.get("name") or None
            if ExternalReference and ExternalReferenceType and url:
                model_component.external_references.add(
                    ExternalReference(
                        reference_type=ExternalReferenceType.OTHER,  # type: ignore[arg-type]
                        url=(XsUri(url) if XsUri else url),  # type: ignore[arg-type]
                        comment=f"Produced: {label} {prod.get('name') or ''} {prod.get('version') or ''}".strip()
                    )
                )
    except Exception:
        pass

    # Register the dependency graph: model depends on its listed components
    try:
        if created_dep_components:
            bom.register_dependency(model_component, created_dep_components)  # type: ignore[attr-defined]
    except Exception:
        # As a fallback, try the explicit Dependency model if available
        try:
            if Dependency is not None and getattr(model_component, 'bom_ref', None):
                root_ref = model_component.bom_ref
                root_dep = Dependency(ref=root_ref)
                for c in created_dep_components:
                    if getattr(c, 'bom_ref', None):
                        root_dep.depends_on.add(c.bom_ref)
                if hasattr(bom, 'dependencies') and hasattr(bom.dependencies, 'update'):
                    bom.dependencies.update([root_dep])  # type: ignore[arg-type]
        except Exception:
            pass

    # Tools metadata: prefer component-based per latest library guidance
    try:
        if cdx_lib_component:
            bom.metadata.tools.components.add(cdx_lib_component())  # type: ignore[call-arg]
        # our generator as a component
        bom.metadata.tools.components.add(Component(
            name='mlmd-to-bom',
            type=ComponentType.APPLICATION,
            version='0.1.0'
        ))
    except Exception:
        # fallback to Tool model for older libs
        try:
            bom.metadata.tools.tools.add(Tool(vendor="mlmd-bom", name="mlmd-to-bom", version="0.1.0"))
        except Exception:
            pass
    return bom


def create_cyclonedx_bom_multi(metadatas: List[Dict[str, Any]]) -> Bom:
    bom = Bom()
    seen_refs: Set[str] = set()

    def add_component(component: Component):
        ref = component.bom_ref or f"{component.name}@{component.version}"
        if ref and ref in seen_refs:
            return
        if ref:
            seen_refs.add(ref)
        bom.components.add(component)

    # Track model refs by name to link lineage
    models_by_name: Dict[str, List[Component]] = {}

    def version_key(v: str) -> tuple:
        parts = []
        for p in (v or "").split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(p)
        return tuple(parts)

    for md in metadatas:
        model_component = Component(
            name=md.get("model_name", "model"),
            version=md.get("version"),
            type=ComponentType.APPLICATION,
            description=f"ML model using {md.get('framework','')} ({md.get('format','')})",
            bom_ref=md.get("uri"),
        )
        add_component(model_component)
        models_by_name.setdefault(md.get("model_name", "model"), []).append(model_component)

        created_dep_components: List[Component] = []
        for dep in md.get("dependencies", []):
            purl_obj = None
            if dep.get("purl"):
                try:
                    purl_obj = PackageURL.from_string(dep["purl"])  # type: ignore[arg-type]
                except Exception:
                    purl_obj = None
            c = Component(
                name=dep.get("name"),
                version=dep.get("version"),
                type=ComponentType.LIBRARY,
                bom_ref=dep.get("purl") or dep.get("uri"),
                purl=purl_obj,
            )
            add_component(c)
            created_dep_components.append(c)

        # Register dependency relation for this model
        try:
            if created_dep_components:
                bom.register_dependency(model_component, created_dep_components)  # type: ignore[attr-defined]
        except Exception:
            try:
                if Dependency is not None and getattr(model_component, 'bom_ref', None):
                    root_ref = model_component.bom_ref
                    root_dep = Dependency(ref=root_ref)
                    for c in created_dep_components:
                        if getattr(c, 'bom_ref', None):
                            root_dep.depends_on.add(c.bom_ref)
                    if hasattr(bom, 'dependencies') and hasattr(bom.dependencies, 'update'):
                        bom.dependencies.update([root_dep])  # type: ignore[arg-type]
            except Exception:
                pass

    # Tools metadata: prefer component-based per latest library guidance
    try:
        if cdx_lib_component:
            bom.metadata.tools.components.add(cdx_lib_component())  # type: ignore[call-arg]
        bom.metadata.tools.components.add(Component(
            name='mlmd-to-bom',
            type=ComponentType.APPLICATION,
            version='0.1.0'
        ))
    except Exception:
        try:
            bom.metadata.tools.tools.add(Tool(vendor="mlmd-bom", name="mlmd-to-bom", version="0.1.0"))
        except Exception:
            pass
    # Attempt to add dependency graph and lineage using official Dependency model if available
    try:
        if Dependency is not None:
            deps_map: Dict[str, Dependency] = {}
            # Initialize Dependency entries for all components
            for c in bom.components:
                ref = getattr(c, "bom_ref", None)
                if not ref:
                    continue
                deps_map.setdefault(ref, Dependency(ref=ref))
            # Link lineage: newer model depends on previous version
            for name, comps in models_by_name.items():
                if len(comps) <= 1:
                    continue
                try:
                    comps.sort(key=lambda x: version_key(x.version or ""))
                except Exception:
                    pass
                for idx in range(1, len(comps)):
                    cur = comps[idx]
                    prev = comps[idx - 1]
                    if getattr(cur, "bom_ref", None) and getattr(prev, "bom_ref", None):
                        deps_map[cur.bom_ref].depends_on.add(prev.bom_ref)
            # Attach to bom
            if hasattr(bom, "dependencies") and hasattr(bom.dependencies, "update"):
                bom.dependencies.update(deps_map.values())  # type: ignore[arg-type]
    except Exception:
        pass
    return bom


def write_cyclonedx_files(bom: Bom, out_json: str = "bom.cyclonedx.json", out_xml: str = "bom.cyclonedx.xml") -> None:
    # Prefer 1.6 when supported
    try:
        schema = CxSchemaVersion.V1_6  # prefer 1.6 when supported
    except Exception:  # pragma: no cover
        schema = CxSchemaVersion.V1_5
    outter_json = make_outputter(bom=bom, output_format=CxOutputFormat.JSON, schema_version=schema)
    outter_xml = make_outputter(bom=bom, output_format=CxOutputFormat.XML, schema_version=schema)
    with open(out_json, "w", encoding="utf-8") as f:
        f.write(outter_json.output_as_string(indent=2))
    with open(out_xml, "w", encoding="utf-8") as f:
        f.write(outter_xml.output_as_string(indent=2))
