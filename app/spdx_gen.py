from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from spdx_tools.spdx.model import Document as SPDXDocument, CreationInfo as SPDXCreationInfo, Package as SPDXPackage
from spdx_tools.spdx.model import Actor, ActorType, Relationship, RelationshipType, SpdxNone
from spdx_tools.spdx.model import ExternalDocumentRef, Checksum, ChecksumAlgorithm
from spdx_tools.spdx.writer.json import json_writer


def create_spdx_document(
    metadata: Dict[str, Any],
    *,
    document_name: Optional[str] = None,
    document_namespace: Optional[str] = None,
    external_document_refs: Optional[List[ExternalDocumentRef]] = None,
) -> SPDXDocument:
    created = datetime.now(timezone.utc)
    creator = Actor(ActorType.TOOL, "mlmd-to-bom/0.1.0", None)
    doc_name = document_name or f"SPDXDoc-{metadata.get('model_name','model')}"
    # Deterministic namespace by default so ExternalDocumentRef can target it reliably
    ns = document_namespace or f"http://spdx.org/spdxdocs/{doc_name}"
    ci = SPDXCreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name=doc_name,
        document_namespace=ns,
        creators=[creator],
        created=created,
    )

    model_pkg = SPDXPackage(
        name=metadata.get("model_name", "model"),
        spdx_id="SPDXRef-Model",
        download_location=SpdxNone(),
        version=metadata.get("version"),
    )

    dep_packages: List[SPDXPackage] = []
    for idx, dep in enumerate(metadata.get("dependencies", []), start=1):
        p = SPDXPackage(
            name=dep.get("name", f"dep{idx}"),
            spdx_id=f"SPDXRef-Dep-{idx}",
            download_location=SpdxNone(),
            version=dep.get("version"),
        )
        dep_packages.append(p)

    # Relationships, including optional lineage to external parent
    relationships: List[Relationship] = [
        Relationship(
            spdx_element_id="SPDXRef-DOCUMENT",
            relationship_type=RelationshipType.DESCRIBES,
            related_spdx_element_id=model_pkg.spdx_id,
        )
    ]

    # Lineage to external parent will be added after attaching the external doc ref below

    doc = SPDXDocument(
        creation_info=ci,
        packages=[model_pkg, *dep_packages],
        files=[],
        snippets=[],
        annotations=[],
        relationships=relationships,
        extracted_licensing_info=[],
    )
    # Best-effort: attach external document references if the installed spdx-tools supports it
    if external_document_refs:
        if hasattr(doc, "external_document_refs"):
            setattr(doc, "external_document_refs", external_document_refs)
        elif hasattr(doc, "external_document_references"):
            setattr(doc, "external_document_references", external_document_refs)
        # Also create an explicit lineage relationship to the model in the external document.
        # We assume the parent model package uses SPDX ID 'SPDXRef-Model' in that document.
        try:
            parent_doc_id = external_document_refs[0].external_document_id  # type: ignore[attr-defined]
            parent_pkg_ref = f"{parent_doc_id}:SPDXRef-Model"
            doc.relationships.append(
                Relationship(
                    spdx_element_id=model_pkg.spdx_id,
                    relationship_type=RelationshipType.DESCENDANT_OF,
                    related_spdx_element_id=parent_pkg_ref,
                )
            )
        except Exception:
            # If the ExternalDocumentRef shape differs, skip lineage relationship silently
            pass
    return doc


def create_spdx_document_multi(metadatas: List[Dict[str, Any]]) -> SPDXDocument:
    created = datetime.now(timezone.utc)
    creator = Actor(ActorType.TOOL, "mlmd-to-bom/0.1.0", None)
    name = "SPDXDoc-mlmd-multi"
    ci = SPDXCreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name=name,
        document_namespace=f"http://spdx.org/spdxdocs/{name}-{int(created.timestamp())}",
        creators=[creator],
        created=created,
    )

    packages: List[SPDXPackage] = []
    relationships: List[Relationship] = []

    # Helper to sort versions in a semantic-ish manner
    def version_key(v: str) -> tuple:
        parts = []
        for p in (v or "").split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(p)
        return tuple(parts)

    # Track model packages by name for lineage linking later
    by_name: Dict[str, List[SPDXPackage]] = {}

    for i, md in enumerate(metadatas, start=1):
        model_spdx_id = f"SPDXRef-Model-{i}"
        model_pkg = SPDXPackage(
            name=md.get("model_name", f"model-{i}"),
            spdx_id=model_spdx_id,
            download_location=SpdxNone(),
            version=md.get("version"),
        )
        packages.append(model_pkg)
        relationships.append(
            Relationship(
                spdx_element_id="SPDXRef-DOCUMENT",
                relationship_type=RelationshipType.DESCRIBES,
                related_spdx_element_id=model_spdx_id,
            )
        )
        by_name.setdefault(md.get("model_name", f"model-{i}"), []).append(model_pkg)

        for j, dep in enumerate(md.get("dependencies", []), start=1):
            dep_id = f"SPDXRef-Dep-{i}-{j}"
            p = SPDXPackage(
                name=dep.get("name", f"dep-{i}-{j}"),
                spdx_id=dep_id,
                download_location=SpdxNone(),
                version=dep.get("version"),
            )
            packages.append(p)
            relationships.append(
                Relationship(
                    spdx_element_id=model_spdx_id,
                    relationship_type=RelationshipType.DEPENDS_ON,
                    related_spdx_element_id=dep_id,
                )
            )

    # Add lineage relationships between models with the same name
    for name, pkgs in by_name.items():
        if len(pkgs) <= 1:
            continue
        # Sort packages by their versionInfo if present
        try:
            pkgs.sort(key=lambda p: version_key(getattr(p, "version", None) or getattr(p, "version_info", "") or ""))
        except Exception:
            pass
        for idx in range(1, len(pkgs)):
            curr = pkgs[idx]
            prev = pkgs[idx - 1]
            relationships.append(
                Relationship(
                    spdx_element_id=curr.spdx_id,
                    relationship_type=RelationshipType.DESCENDANT_OF,
                    related_spdx_element_id=prev.spdx_id,
                )
            )

    doc = SPDXDocument(
        creation_info=ci,
        packages=packages,
        files=[],
        snippets=[],
        annotations=[],
        relationships=relationships,
        extracted_licensing_info=[],
    )
    return doc


def write_spdx_json(doc: SPDXDocument, out_path: str = "bom.spdx.json") -> None:
    json_writer.write_document_to_file(doc, out_path)
