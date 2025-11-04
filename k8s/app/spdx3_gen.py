# SPDX generation is deprecated for now. Do not use this module.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
import logging

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _doc_ns(name: str, version: int | str = 1) -> str:
    # Use a URN namespace stable across runs for demo purposes
    return f"urn:spdx:doc:{name}:{version}"


def create_spdx3_document(
    metadata: Dict[str, Any],
    *,
    document_name: Optional[str] = None,
    document_version: int | str = 1,
    parent_doc_name: Optional[str] = None,
    parent_doc_version: int | str = 1,
    # child lineage intentionally not emitted in this implementation to avoid
    # forward references; keep params for backward-compat but ignore them
    child_doc_name: Optional[str] = None,
    child_doc_version: int | str = 1,
) -> Dict[str, Any]:
    """
    Create an SPDX 3.0 JSON document for a single model with optional lineage to a parent document.
    Emits document-qualified identifiers and externalMaps for cross-doc references.
    """
    model_name = metadata.get("model_name", "model")
    version = metadata.get("version", "")
    doc_name = document_name or f"{model_name}-{version}".strip("-")
    doc_ns = _doc_ns(doc_name, document_version)

    elements: List[Dict[str, Any]] = []

    doc_elem = {
        "type": "SpdxDocument",
        "id": "doc",
        "name": doc_name,
        "documentNamespace": doc_ns,
        "specVersion": "SPDX-3.0",
        "creationInfo": {
            "created": _iso_now(),
            "createdBy": [{"type": "Tool", "name": "mlmd-to-bom", "version": "0.1.0"}],
        },
    }
    elements.append(doc_elem)

    pkg_id = "SPDXRef-Model"
    elements.append(
        {
            "type": "Package",
            "id": pkg_id,
            "name": model_name,
            "version": version or None,
            "definedIn": "doc",
            "properties": [
                {"name": f"ml:{k}", "value": str(v)} for k, v in (metadata.get("properties") or {}).items()
            ] or None,
        }
    )

    # Dependencies as Package elements — lineage handled via Relationship
    for idx, dep in enumerate(metadata.get("dependencies", []), start=1):
        elements.append(
            {
                "type": "Package",
                "id": f"SPDXRef-Dep-{idx}",
                "name": dep.get("name"),
                "version": dep.get("version"),
                "definedIn": "doc",
                "properties": [
                    {"name": f"ml:{k}", "value": str(v)} for k, v in (dep.get("properties") or {}).items()
                ] or None,
            }
        )
        elements.append(
            {
                "type": "Relationship",
                "id": f"rel-dep-{idx}",
                "from": f"doc:{pkg_id}",
                "relationshipType": "dependsOn",
                "to": f"doc:SPDXRef-Dep-{idx}",
                "definedIn": "doc",
            }
        )

    # Produced artifacts (e.g., evaluation report, container image) as packages with relationships
    for pidx, prod in enumerate(metadata.get("produced", []), start=1):
        prod_id = f"SPDXRef-Prod-{pidx}"
        elements.append(
            {
                "type": "Package",
                "id": prod_id,
                "name": prod.get("name") or prod.get("type") or f"Produced-{pidx}",
                "version": prod.get("version"),
                "definedIn": "doc",
                "properties": [
                    {"name": f"ml:{k}", "value": str(v)} for k, v in (prod.get("properties") or {}).items()
                ] or None,
            }
        )
        elements.append(
            {
                "type": "Relationship",
                "id": f"rel-produced-{pidx}",
                "from": f"doc:{pkg_id}",
                # model has output artifact from downstream stages
                "relationshipType": "hasOutput",
                "to": f"doc:{prod_id}",
                "definedIn": "doc",
            }
        )

    external_maps: List[Dict[str, Any]] = []

    # Lineage to parent model in another document
    if parent_doc_name:
        parent_ns = _doc_ns(parent_doc_name, parent_doc_version)
        # Relationship referencing external document's package
        elements.append(
            {
                "type": "Relationship",
                "id": "rel-lineage-parent",
                "from": f"doc:{pkg_id}",
                "relationshipType": "descendantOf",
                "to": f"doc-parent:SPDXRef-Model",
                "definedIn": "doc",
            }
        )
        # External map providing where to find doc-parent
        # In a full implementation, include verification info (e.g., sha256) of the external doc
        external_maps.append(
            {
                "externalDocumentId": "doc-parent",
                "documentNamespace": parent_ns,
                # Optional: location and verification
                # "location": "https://example.com/path/to/parent.spdx.json",
                # "checksums": [{"algorithm": "sha256", "value": "..."}],
            }
        )
        logger.debug("added SPDX lineage", extra={
                     "doc": doc_name, "parent": parent_doc_name})

    # Note: We intentionally do not add an 'ancestorOf' relationship from the current
    # document to its child. Typical practice mirrors CycloneDX: only the newer document
    # links back to its parent (descendantOf). This avoids forward references and keeps
    # lineage unidirectional for simplicity.

    doc = {
        "spdxVersion": "SPDX-3.0",
        "documentNamespace": doc_ns,
        "elements": elements,
        "externalMaps": external_maps or None,
    }
    logger.info("created SPDX3 document", extra={
                "name": doc_name, "elements": len(elements)})
    return doc


def create_spdx3_document_multi(metadatas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create an SPDX 3.0 JSON document containing multiple models and lineage edges between versions."""
    name = "mlmd-multi"
    doc_ns = _doc_ns(name, 1)

    def version_key(v: str) -> tuple:
        parts = []
        for p in (v or "").split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(p)
        return tuple(parts)

    elements: List[Dict[str, Any]] = [
        {
            "type": "SpdxDocument",
            "id": "doc",
            "name": name,
            "documentNamespace": doc_ns,
            "specVersion": "SPDX-3.0",
            "creationInfo": {
                "created": _iso_now(),
                "createdBy": [{"type": "Tool", "name": "mlmd-to-bom", "version": "0.1.0"}],
            },
        }
    ]

    # Build model elements and map by name for lineage linking
    models_by_name: Dict[str, List[str]] = {}
    for i, md in enumerate(metadatas, start=1):
        pkg_id = f"SPDXRef-Model-{i}"
        elements.append(
            {
                "type": "Package",
                "id": pkg_id,
                "name": md.get("model_name", f"model-{i}"),
                "version": md.get("version"),
                "definedIn": "doc",
            }
        )
        key = md.get("model_name", f"model-{i}")
        models_by_name.setdefault(key, []).append(pkg_id)

        # Dependencies for each model
        for j, dep in enumerate(md.get("dependencies", []), start=1):
            dep_id = f"SPDXRef-Dep-{i}-{j}"
            elements.append(
                {
                    "type": "Package",
                    "id": dep_id,
                    "name": dep.get("name"),
                    "version": dep.get("version"),
                    "definedIn": "doc",
                }
            )
            elements.append(
                {
                    "type": "Relationship",
                    "id": f"rel-dep-{i}-{j}",
                    "from": f"doc:{pkg_id}",
                    "relationshipType": "dependsOn",
                    "to": f"doc:{dep_id}",
                    "definedIn": "doc",
                }
            )

    # Lineage within the same document
    for _, pkg_ids in models_by_name.items():
        if len(pkg_ids) <= 1:
            continue
        # Stable order based on numeric version suffix if present in id
        # Note: we could sort by actual version metadata if needed
        for idx in range(1, len(pkg_ids)):
            elements.append(
                {
                    "type": "Relationship",
                    "id": f"rel-lineage-{idx}",
                    "from": f"doc:{pkg_ids[idx]}",
                    "relationshipType": "descendantOf",
                    "to": f"doc:{pkg_ids[idx-1]}",
                    "definedIn": "doc",
                }
            )

    doc = {
        "spdxVersion": "SPDX-3.0",
        "documentNamespace": doc_ns,
        "elements": elements,
    }
    logger.info("created SPDX3 multi document", extra={
                "models": len(models_by_name), "elements": len(elements)})
    return doc
