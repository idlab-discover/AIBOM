from __future__ import annotations

from typing import Any, Dict
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.tool import Tool
from cyclonedx.output import make_outputter, OutputFormat as CxOutputFormat
from cyclonedx.output import SchemaVersion as CxSchemaVersion
from packageurl import PackageURL


def create_cyclonedx_bom(metadata: Dict[str, Any]) -> Bom:
    bom = Bom()
    model_component = Component(
        name=metadata.get("model_name", "model"),
        version=metadata.get("version"),
        type=ComponentType.APPLICATION,
        description=f"ML model using {metadata.get('framework','')} ({metadata.get('format','')})",
        bom_ref=metadata.get("uri"),
    )
    bom.components.add(model_component)

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
        bom.components.add(c)

    bom.metadata.tools.tools.add(Tool(vendor="mlmd-bom", name="mlmd-to-bom", version="0.1.0"))
    return bom


def write_cyclonedx_files(bom: Bom, out_json: str = "bom.cyclonedx.json", out_xml: str = "bom.cyclonedx.xml") -> None:
    outter_json = make_outputter(bom=bom, output_format=CxOutputFormat.JSON, schema_version=CxSchemaVersion.V1_5)
    outter_xml = make_outputter(bom=bom, output_format=CxOutputFormat.XML, schema_version=CxSchemaVersion.V1_5)
    with open(out_json, "w", encoding="utf-8") as f:
        f.write(outter_json.output_as_string())
    with open(out_xml, "w", encoding="utf-8") as f:
        f.write(outter_xml.output_as_string())
