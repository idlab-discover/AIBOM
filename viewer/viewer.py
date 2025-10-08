# This file mirrors app/viewer.py but lives in a separate image context.
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import time
from typing import Dict, Set, Tuple, Any

import networkx as nx  # type: ignore
from pyvis.network import Network  # type: ignore

OUTPUT_ROOT = Path("/app/output").resolve()  # shared volume mount from compose
CX_DIR = OUTPUT_ROOT / "cyclonedx"
SPDX_DIR = OUTPUT_ROOT / "spdx"
VIEW_DIR = OUTPUT_ROOT / "viewer"
VIEW_HTML = VIEW_DIR / "index.html"
VIEW_HTML_CX = VIEW_DIR / "cyclonedx.html"
VIEW_HTML_SPDX = VIEW_DIR / "spdx.html"


def _safe_node_id(prefix: str, name: str | None, version: str | None) -> str:
    n = (name or "unknown").strip()
    v = (version or "").strip()
    return f"{prefix}:{n}@{v}" if v else f"{prefix}:{n}"


def _ensure_dirs() -> None:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)


def parse_cyclonedx(g: nx.DiGraph, details: Dict[str, Dict[str, Any]]) -> None:
    bomlink_to_model: Dict[str, str] = {}
    for p in sorted(CX_DIR.glob("*.cyclonedx.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                bom = json.load(fh)
        except Exception:
            continue
        serial = bom.get("serialNumber")
        bom_version = bom.get("version", 1)
        meta = bom.get("metadata", {})
        model_comp = meta.get("component") or None
        if not model_comp or model_comp.get("type") != "application":
            for c in bom.get("components", []):
                if c.get("type") == "application":
                    model_comp = c
                    break
        if not model_comp:
            continue
        model_id = _safe_node_id("model", model_comp.get("name"), model_comp.get("version"))
        bom_ref = model_comp.get("bom-ref")
        if serial and bom_ref:
            key = f"urn:cdx:{serial}/{bom_version}#{bom_ref}"
            bomlink_to_model[key] = model_id

    for p in sorted(CX_DIR.glob("*.cyclonedx.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                bom = json.load(fh)
        except Exception:
            continue
        meta = bom.get("metadata", {})
        model_comp = meta.get("component") or None
        if not model_comp or model_comp.get("type") != "application":
            for c in bom.get("components", []):
                if c.get("type") == "application":
                    model_comp = c
                    break
        if not model_comp:
            continue
        model_id = _safe_node_id("model", model_comp.get("name"), model_comp.get("version"))
        g.add_node(model_id, label=f"{model_comp.get('name')}\n{model_comp.get('version')}", title=str(p.name), color="#1976d2", shape="dot", size=18)
        # Save component JSON and file link for details panel
        rel_path = os.path.relpath(p, VIEW_DIR)
        details.setdefault(model_id, {})["cx"] = model_comp
        details[model_id]["cx_file"] = rel_path

        comp_by_ref = {c.get("bom-ref"): c for c in bom.get("components", []) if c.get("bom-ref")}
        model_ref = model_comp.get("bom-ref")
        dep_refs: Set[str] = set()
        for dep in bom.get("dependencies", []):
            ref = dep.get("ref")
            if ref == model_ref:
                for d in dep.get("dependsOn", []) or []:
                    dep_refs.add(d)
        for r in dep_refs:
            c = comp_by_ref.get(r, {})
            name = c.get("name") or r
            version = c.get("version")
            if isinstance(r, str) and r.startswith("data://"):
                dep_id = _safe_node_id("data", name, version)
                color = "#2e7d32"
            else:
                dep_id = _safe_node_id("lib", name, version)
                color = "#616161"
            if not g.has_node(dep_id):
                g.add_node(dep_id, label=f"{name}\n{version or ''}", title=r, color=color, shape="box", size=12)
            # Save dependency component JSON for details panel
            if c:
                details.setdefault(dep_id, {})["cx"] = c
                details[dep_id]["cx_file"] = rel_path
            g.add_edge(model_id, dep_id, color="#90a4ae", arrows="to", title="depends_on")

        extrefs = (model_comp.get("externalReferences") or [])
        for er in extrefs:
            if er.get("type") == "bom":
                parent_key = er.get("url")
                parent_id = bomlink_to_model.get(parent_key)
                if parent_id:
                    g.add_edge(parent_id, model_id, color="#f57c00", dashes=True, arrows="to", title="lineage:parent→child")


def parse_spdx3(g: nx.DiGraph, details: Dict[str, Dict[str, Any]]) -> None:
    ns_to_model: Dict[str, str] = {}
    # First pass: map documentNamespace -> model node id
    for p in sorted(SPDX_DIR.glob("*.spdx3.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        ns = doc.get("documentNamespace")
        model = None
        for el in doc.get("elements", []):
            if el.get("type") == "Package" and el.get("id") == "SPDXRef-Model":
                model = el
                break
        if ns and model:
            ns_to_model[ns] = _safe_node_id("model", model.get("name"), model.get("version"))

    # Second pass: build nodes and edges, and details
    for p in sorted(SPDX_DIR.glob("*.spdx3.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        packages = {el.get("id"): el for el in doc.get("elements", []) if el.get("type") == "Package"}
        model = packages.get("SPDXRef-Model")
        if not model:
            continue
        model_id = _safe_node_id("model", model.get("name"), model.get("version"))
        if not g.has_node(model_id):
            g.add_node(model_id, label=f"{model.get('name')}\n{model.get('version')}", title=str(p.name), color="#1976d2", shape="dot", size=18)
        # Save SPDX package JSON and file link
        rel_path = os.path.relpath(p, VIEW_DIR)
        details.setdefault(model_id, {})["spdx"] = model
        details[model_id]["spdx_file"] = rel_path

        for el in doc.get("elements", []):
            if el.get("type") != "Relationship":
                continue
            rel_type = el.get("relationshipType")
            if rel_type == "dependsOn" and el.get("from") == "doc:SPDXRef-Model":
                to_id = el.get("to", "")
                dep_pkg = packages.get(to_id.split(":", 1)[-1])
                if not dep_pkg:
                    continue
                name = dep_pkg.get("name")
                version = dep_pkg.get("version")
                dep_node = _safe_node_id("lib", name, version)
                color = "#616161"
                if name and "dataset" in (name or "").lower():
                    dep_node = _safe_node_id("data", name, version)
                    color = "#2e7d32"
                if not g.has_node(dep_node):
                    g.add_node(dep_node, label=f"{name}\n{version or ''}", color=color, shape="box", size=12)
                # Save dep package details
                details.setdefault(dep_node, {})["spdx"] = dep_pkg
                details[dep_node]["spdx_file"] = rel_path
                g.add_edge(model_id, dep_node, color="#90a4ae", arrows="to", title="depends_on")
            elif rel_type == "descendantOf" and el.get("from") == "doc:SPDXRef-Model":
                to_target = el.get("to", "")
                ext_maps = doc.get("externalMaps") or []
                parent_ns = None
                for m in ext_maps:
                    if m.get("externalDocumentId") == to_target.split(":", 1)[0]:
                        parent_ns = m.get("documentNamespace")
                        break
                if parent_ns:
                    parent_id = ns_to_model.get(parent_ns)
                    if parent_id:
                        g.add_edge(parent_id, model_id, color="#f57c00", dashes=True, arrows="to", title="lineage:parent→child")


def build_graph() -> Tuple[nx.DiGraph, Dict[str, Dict[str, Any]]]:
    g = nx.DiGraph()
    details: Dict[str, Dict[str, Any]] = {}
    if CX_DIR.exists():
        parse_cyclonedx(g, details)
    if SPDX_DIR.exists():
        parse_spdx3(g, details)
    return g, details


def _parse_model_id(node_id: str) -> Tuple[str, str]:
    # model:name@version
    try:
        prefix, rest = node_id.split(":", 1)
        if "@" in rest:
            name, ver = rest.rsplit("@", 1)
        else:
            name, ver = rest, ""
        return name, ver
    except Exception:
        return node_id, ""


def apply_positions(g: nx.DiGraph) -> Dict[str, Tuple[float, float]]:
    # Place model chains in columns by model name, versions in rows; deps in a circle around model
    model_nodes = [n for n in g.nodes if str(n).startswith("model:")]
    groups: Dict[str, list] = {}
    for n in model_nodes:
        name, ver = _parse_model_id(n)
        groups.setdefault(name, []).append((n, ver))
    # Sort columns by name
    col_names = sorted(groups.keys())
    X_SP = 600
    Y_SP = 280
    pos: Dict[str, Tuple[float, float]] = {}
    for ci, name in enumerate(col_names):
        chain = groups[name]
        # Sort by version string (best-effort)
        chain.sort(key=lambda t: t[1])
        for ri, (node, _ver) in enumerate(chain):
            x = ci * X_SP
            y = ri * Y_SP
            pos[node] = (x, y)
            # Collect direct dependencies
            deps = [v for u, v, d in g.out_edges(node, data=True) if d.get("title") == "depends_on"]
            if not deps:
                continue
            R = 160 + 10 * len(deps)
            for idx, dep in enumerate(deps):
                if dep in pos:
                    continue
                angle = 2 * math.pi * (idx / len(deps))
                dx = x + R * math.cos(angle)
                dy = y + R * math.sin(angle)
                pos[dep] = (dx, dy)
    return pos


def render_html(g: nx.DiGraph, out_file: Path, details: Dict[str, Dict[str, Any]], mode: str) -> None:
    _ensure_dirs()
    net = Network(height="800px", width="100%", directed=True, bgcolor="#ffffff", font_color="#333333")
    net.barnes_hut(gravity=-4000, central_gravity=0.2, spring_length=150, spring_strength=0.03, damping=0.8)
    for n, data in g.nodes(data=True):
        # apply positions if available
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            net.add_node(n, **{**data, "x": x, "y": y, "physics": False, "fixed": True})
        else:
            net.add_node(n, **data)
    for u, v, data in g.edges(data=True):
        net.add_edge(u, v, **data)
    # No hierarchical layout: we place dependencies around models via fixed positions
    net.set_options(
        """
        {
          "interaction": {"hover": true},
          "physics": {"enabled": false},
          "edges": {"smooth": {"type": "dynamic"}}
        }
        """
    )
    net.write_html(str(out_file), local=False)
    for d in [Path.cwd() / "lib", out_file.parent / "lib"]:
        try:
            if d.exists() and d.is_dir():
                shutil.rmtree(d)
        except Exception:
            pass
    # Inject details panel and click handler
    try:
        with open(out_file, "r", encoding="utf-8") as fh:
            html = fh.read()
        panel = (
            "<style>\n"
            "#detailsPanel{position:fixed;right:0;top:0;width:38%;height:100%;overflow:auto;background:#fafafa;border-left:1px solid #ddd;padding:10px;font-family:monospace;}\n"
            "#detailsPanel h3{font-family:sans-serif;margin:8px 0;}\n"
            "#detailsPanel pre{background:#fff;border:1px solid #eee;padding:8px;white-space:pre-wrap;}\n"
            "#detailsPanel .links a{display:inline-block;margin-right:8px;}\n"
            "#canvasWrap{width:62%;} .card{max-width:62vw;}\n"
            "</style>\n"
            "<div id=\"detailsPanel\"><h3>Details</h3>"
            + ("<div class=\"links\">Click a model to view full BOM(s).</div>" )
            + ("<h4>CycloneDX</h4><pre id=\"cxJson\">Select a node...</pre>" if mode in ("combined","cx") else "")
            + ("<h4>SPDX</h4><pre id=\"spdxJson\"></pre>" if mode in ("combined","spdx") else "")
            + "<div class=\"links\" id=\"bomLinks\"></div>"
            + "</div>"
        )
        # Place panel before closing body
        insert_at = html.rfind("</body>")
        details_js = json.dumps(details)
        parts: list[str] = []
        parts.append("<script>\n")
        parts.append("const DETAILS = " + details_js + ";\n")
        parts.append("function showDetails(nodeId){\n")
        parts.append("  const d = DETAILS[nodeId] || {};\n")
        if mode in ("combined", "cx"):
            parts.append("  const cx = d.cx ? JSON.stringify(d.cx, null, 2) : 'N/A';\n  var cxEl = document.getElementById('cxJson'); if(cxEl){cxEl.textContent = cx;}\n")
        if mode in ("combined", "spdx"):
            parts.append("  const spdx = d.spdx ? JSON.stringify(d.spdx, null, 2) : 'N/A';\n  var sEl = document.getElementById('spdxJson'); if(sEl){sEl.textContent = spdx;}\n")
        parts.append("  var links = [];\n")
        if mode in ("combined", "cx"):
            parts.append("  if(d.cx_file){ links.push('<a href=\\''+d.cx_file+'\\' target=\\'_blank\\'>Open CycloneDX</a>'); }\n")
        if mode in ("combined", "spdx"):
            parts.append("  if(d.spdx_file){ links.push('<a href=\\''+d.spdx_file+'\\' target=\\'_blank\\'>Open SPDX</a>'); }\n")
        parts.append("  var bl = document.getElementById('bomLinks'); if(bl){ bl.innerHTML = links.join(' ');}\n")
        parts.append("}\n")
        parts.append("if (typeof network !== 'undefined'){\n")
        parts.append("  network.on('selectNode', function(params){ if(params.nodes && params.nodes.length){ showDetails(params.nodes[0]); }});\n")
        parts.append("  network.on('doubleClick', function(params){\n")
        parts.append("    if(params.nodes && params.nodes.length){\n")
        parts.append("      const nodeId = params.nodes[0];\n")
        parts.append("      if(nodeId && nodeId.startsWith('model:')){\n")
        if mode in ("combined", "cx"):
            parts.append("        const d = DETAILS[nodeId] || {}; if(d.cx_file){ window.open(d.cx_file, '_blank'); }\n")
        if mode in ("combined", "spdx"):
            parts.append("        const d2 = DETAILS[nodeId] || {}; if(d2.spdx_file){ window.open(d2.spdx_file, '_blank'); }\n")
        parts.append("      }\n")
        parts.append("    }\n")
        parts.append("  });\n")
        parts.append("}\n")
        parts.append("</script>\n")
        script = "".join(parts)
        new_html = html[:insert_at] + panel + script + html[insert_at:]
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(new_html)
    except Exception:
        pass


def main() -> int:
    tries = 0
    while tries < 20:
        cx_files = list(CX_DIR.glob("*.cyclonedx.json")) if CX_DIR.exists() else []
        spdx_files = list(SPDX_DIR.glob("*.spdx3.json")) if SPDX_DIR.exists() else []
        if cx_files or spdx_files:
            break
        time.sleep(0.5)
        tries += 1
    g_all, details_all = build_graph()
    # Apply positions for combined view
    pos = apply_positions(g_all)
    for n, (x, y) in pos.items():
        g_all.nodes[n]["x"] = x
        g_all.nodes[n]["y"] = y
    render_html(g_all, VIEW_HTML, details_all, mode="combined")
    # CycloneDX-only
    g_cx = nx.DiGraph()
    details_cx: Dict[str, Dict[str, Any]] = {}
    if CX_DIR.exists():
        parse_cyclonedx(g_cx, details_cx)
        pos_cx = apply_positions(g_cx)
        for n, (x, y) in pos_cx.items():
            g_cx.nodes[n]["x"] = x
            g_cx.nodes[n]["y"] = y
        render_html(g_cx, VIEW_HTML_CX, details_cx, mode="cx")
    # SPDX-only
    g_spdx = nx.DiGraph()
    details_spdx: Dict[str, Dict[str, Any]] = {}
    if SPDX_DIR.exists():
        parse_spdx3(g_spdx, details_spdx)
        pos_sd = apply_positions(g_spdx)
        for n, (x, y) in pos_sd.items():
            g_spdx.nodes[n]["x"] = x
            g_spdx.nodes[n]["y"] = y
        render_html(g_spdx, VIEW_HTML_SPDX, details_spdx, mode="spdx")
    print(f"Viewer written to {VIEW_HTML}\nCycloneDX-only: {VIEW_HTML_CX}\nSPDX-only: {VIEW_HTML_SPDX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
