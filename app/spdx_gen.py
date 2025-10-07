from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from spdx_tools.spdx.model import Document as SPDXDocument, CreationInfo as SPDXCreationInfo, Package as SPDXPackage
from spdx_tools.spdx.model import Actor, ActorType, Relationship, RelationshipType, SpdxNone
from spdx_tools.spdx.writer.json import json_writer


def create_spdx_document(metadata: Dict[str, Any]) -> SPDXDocument:
    created = datetime.now(timezone.utc)
    creator = Actor(ActorType.TOOL, "mlmd-to-bom/0.1.0", None)
    ci = SPDXCreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name=f"SPDXDoc-{metadata.get('model_name','model')}",
        document_namespace=f"http://spdx.org/spdxdocs/{metadata.get('model_name','model')}-{int(created.timestamp())}",
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

    rel = Relationship(
        spdx_element_id="SPDXRef-DOCUMENT",
        relationship_type=RelationshipType.DESCRIBES,
        related_spdx_element_id=model_pkg.spdx_id,
    )

    doc = SPDXDocument(
        creation_info=ci,
        packages=[model_pkg, *dep_packages],
        files=[],
        snippets=[],
        annotations=[],
        relationships=[rel],
        extracted_licensing_info=[],
    )
    return doc


def write_spdx_json(doc: SPDXDocument, out_path: str = "bom.spdx.json") -> None:
    json_writer.write_document_to_file(doc, out_path)
