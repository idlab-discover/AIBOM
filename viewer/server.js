#!/usr/bin/env node

// Minimal live viewer server: watches /app/output/cyclonedx, rebuilds in-memory graph, serves HTML and JSON endpoints.
import express from 'express';
import path from 'path';
import fs from 'fs';
import chokidar from 'chokidar';
import { fileURLToPath } from 'url';

const __DIRNAME = path.dirname(fileURLToPath(import.meta.url));
const VIS_PKG = path.join(__DIRNAME, 'node_modules', 'vis-network');
const OUTPUT_ROOT = '/app/output';
const CX_DIR = path.join(OUTPUT_ROOT, 'cyclonedx');

const app = express();
const PORT = process.env.PORT || 8080;

function readJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } }
function listJson(dir) { try { return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => path.join(dir, f)); } catch { return []; } }
function relFromView(p) { return path.relative(OUTPUT_ROOT, p); }

function buildGraph() {
  const g = { nodes: {}, edges: [] };
  const details = {};
  const files = listJson(CX_DIR);
  const bomRefToNode = {};
  const entries = [];

  // Pass 1: create nodes and index by bom-ref
  for (const fp of files) {
    const bom = readJson(fp); if (!bom) continue;
    const rel = relFromView(fp);
    const metaComp = (bom.metadata || {}).component;
    if (!metaComp || !metaComp['bom-ref']) continue;
    const bomRef = metaComp['bom-ref'];
    const kind = metaComp.type === 'application' ? 'model' : 'dataset';
    const name = metaComp.name || 'unknown';
    const version = metaComp.version || '';
    const nodeId = bomRef;
    g.nodes[nodeId] = {
      id: nodeId,
      label: `${name}\n${version}`,
      color: kind === 'model' ? '#1976d2' : '#2e7d32',
      shape: 'dot',
      size: kind === 'model' ? 18 : 16
    };
    details[nodeId] = { cx: metaComp, cx_file: rel };
    bomRefToNode[bomRef] = nodeId;
    entries.push({ fp, rel, kind, nodeId, metaComp, bom });
  }

  // Pass 2: edges from externalReferences and model dependencies
  for (const e of entries) {
    const { bom, metaComp, nodeId, kind } = e;
    // ExternalReferences-based edges (lineage, model-dataset)
    for (const er of (metaComp.externalReferences || [])) {
      if (!er || er.type !== 'bom' || !er.url) continue;
      let targetRef = String(er.url).startsWith('urn:mlmd-bom-ref:') ? String(er.url).slice('urn:mlmd-bom-ref:'.length) : String(er.url);
      if (!bomRefToNode[targetRef]) continue;
      const comment = String(er.comment || '').toLowerCase();
      if (kind === 'model' && comment.includes('parent') && comment.includes('model')) {
        g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
      } else if (kind === 'model' && comment.includes('child') && comment.includes('model')) {
        g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
      } else if (kind === 'dataset' && comment.includes('parent') && comment.includes('dataset')) {
        g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
      } else if (kind === 'dataset' && comment.includes('child') && comment.includes('dataset')) {
        g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
      } else if (kind === 'model' && comment.includes('uses dataset')) {
        g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#c62828', arrows: 'to', title: 'uses_dataset' });
      } else if (kind === 'dataset' && comment.includes('used by model')) {
        g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#c62828', arrows: 'to', title: 'uses_dataset' });
      }
    }
    // Model dependencies (library edges)
    if (kind === 'model' && Array.isArray(bom.dependencies)) {
      // Find the dependency entry for the model's own bom-ref
      const modelDep = bom.dependencies.find(dep => dep.ref === nodeId);
      if (modelDep && Array.isArray(modelDep.dependsOn)) {
        // Find all components in the BOM (should be libraries)
        const byRef = {};
        for (const c of (bom.components || [])) {
          if (c['bom-ref']) byRef[c['bom-ref']] = c;
        }
        for (const depRef of modelDep.dependsOn) {
          // Add node for the library if not present
          if (!g.nodes[depRef]) {
            const c = byRef[depRef] || {};
            const name = c.name || depRef;
            const version = c.version || '';
            g.nodes[depRef] = {
              id: depRef,
              label: `${name}\n${version}`,
              color: '#616161',
              shape: 'box',
              size: 12
            };
            details[depRef] = { cx: c, cx_file: e.rel };
          }
          g.edges.push({ from: nodeId, to: depRef, color: '#90a4ae', arrows: 'to', title: 'depends_on' });
        }
      }
    }
  }
  return { g, details };
}

function makeHtml({ g, details }) {
  const nodes = Object.values(g.nodes);
  const edges = g.edges;
  const data = { nodes, edges, details };
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <meta http-equiv="Pragma" content="no-cache" />
  <meta http-equiv="Expires" content="0" />
  <title>BOM Viewer - Live</title>
  <style>
    body { margin:0; font-family: sans-serif; }
    #container { display:flex; height:100vh; }
    #graph { flex: 0 0 62vw; height:100vh; }
    #panel { flex: 1; border-left: 1px solid #ddd; background:#fafafa; padding:10px; overflow:auto; }
    pre { background:#fff; border:1px solid #eee; padding:8px; white-space:pre-wrap; }
    .links a{ margin-right:8px; }
  </style>
  <script src="/assets/vis-network.min.js"></script>
  <link rel="stylesheet" href="/assets/vis-network.min.css"/>
</head>
<body>
  <div id="container">
    <div id="graph"></div>
    <div id="panel">
      <h3>Details</h3>
      <div class="links">Click a model or dataset to open full BOM(s).</div>
      <h4>CycloneDX</h4><pre id="cxJson">Select a node...</pre>
      <div class="links" id="bomLinks"></div>
    </div>
  </div>
  <script>
    const DATA = ${JSON.stringify(data)};
    const container = document.getElementById('graph');
    const network = new vis.Network(container, { nodes: new vis.DataSet(DATA.nodes), edges: new vis.DataSet(DATA.edges) }, {
      interaction: { hover: true, dragNodes: true },
      physics: {enabled: false},
      edges: { smooth: { type: 'dynamic' } }
    });
    function showDetails(id){
      const d = (DATA.details||{})[id] || {};
      var cxEl = document.getElementById('cxJson');
      if(cxEl) cxEl.textContent = d.cx ? JSON.stringify(d.cx,null,2) : 'N/A';
      var bl = document.getElementById('bomLinks');
      if(bl){
        var links = [];
        if(d.cx_file)
          links.push('<a target="_blank" href="'+('/output/'+d.cx_file)+'">Open CycloneDX</a>');
        bl.innerHTML = links.join(' ');
      }
    }
    network.on('selectNode', p=>{ if(p.nodes && p.nodes.length) showDetails(p.nodes[0]); });
    network.on('doubleClick', p=>{ if(p.nodes && p.nodes.length){ const id=p.nodes[0]; const d=(DATA.details||{})[id]||{}; if(d.cx_file) window.open('/output/'+d.cx_file,'_blank'); } });
  </script>
</body>
</html>`;
}

let cache = { html: '' };
function rebuild() {
  try {
    const { g, details } = buildGraph();
    cache.html = makeHtml({ g, details });
  } catch (e) {
    cache.html = `<pre>Failed to build graph: ${e}</pre>`;
  }
}

rebuild();
const watcher = chokidar.watch([CX_DIR], { ignoreInitial: true, depth: 1 });
watcher.on('add', rebuild).on('change', rebuild).on('unlink', rebuild);

app.get('/', (req, res) => { if (!cache.html) rebuild(); res.set('Cache-Control', 'no-store'); return res.send(cache.html); });
app.use('/output', express.static(OUTPUT_ROOT, { etag: false, lastModified: false, cacheControl: false, setHeaders: res => { res.set('Cache-Control', 'no-store'); } }));
app.get('/assets/vis-network.min.js', (req, res) => {
  const jsPath = path.join(VIS_PKG, 'dist', 'vis-network.min.js');
  if (!fs.existsSync(jsPath)) return res.status(404).send('vis-network js not found');
  res.type('application/javascript');
  return res.sendFile(jsPath);
});
app.get('/assets/vis-network.min.css', (req, res) => {
  const cssPath = path.join(VIS_PKG, 'styles', 'vis-network.min.css');
  if (!fs.existsSync(cssPath)) return res.status(404).send('vis-network css not found');
  res.type('text/css');
  return res.sendFile(cssPath);
});

app.listen(PORT, () => { console.log(`viewer server running at http://localhost:${PORT}`); });
