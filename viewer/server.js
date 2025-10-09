#!/usr/bin/env node
// Minimal live viewer server: watches /app/output/{cyclonedx,spdx}, rebuilds in-memory graph, serves HTML and JSON endpoints.
import express from 'express';
import path from 'path';
import fs from 'fs';
import chokidar from 'chokidar';
import { fileURLToPath } from 'url';

// Locate node_modules so we can serve vis-network directly without copying
const __DIRNAME = path.dirname(fileURLToPath(import.meta.url));
const VIS_PKG = path.join(__DIRNAME, 'node_modules', 'vis-network');
function firstExisting(paths) {
  for (const p of paths) { try { if (fs.existsSync(p)) return p; } catch { } }
  return null;
}

const OUTPUT_ROOT = '/app/output';
const CX_DIR = path.join(OUTPUT_ROOT, 'cyclonedx');

const app = express();
const PORT = process.env.PORT || 8080;

// --- Logging setup (plain or json) ---
const LOG_LEVEL = (process.env.LOG_LEVEL || 'info').toLowerCase();
const LOG_FORMAT = (process.env.LOG_FORMAT || 'plain').toLowerCase();
const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const THRESH = LEVELS[LOG_LEVEL] ?? LEVELS.info;
function log(level, msg, meta) {
  const lvl = LEVELS[level] ?? LEVELS.info;
  if (lvl < THRESH) return;
  const ts = new Date().toISOString();
  if (LOG_FORMAT === 'json') {
    const obj = { ts, level, msg, ...(meta || {}) };
    // Avoid circular and big objects
    try {
      console.log(JSON.stringify(obj));
    } catch {
      console.log(JSON.stringify({ ts, level, msg }));
    }
  } else {
    const m = meta ? ` ${JSON.stringify(meta)}` : '';
    console.log(`${ts} ${level.toUpperCase()} viewer: ${msg}${m}`);
  }
}

function readJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { log('debug', 'failed to parse json', { file: p, error: String(e) }); return null; } }
function listJson(dir) { try { return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => path.join(dir, f)); } catch { return []; } }
function safeNodeId(prefix, name, version) { const n = (name || 'unknown').trim(); const v = (version || '').trim(); return v ? `${prefix}:${n}@${v}` : `${prefix}:${n}`; }
function relFromView(p) { return path.relative(OUTPUT_ROOT, p); }

function buildGraph() {
  const g = { nodes: {}, edges: [] };
  const details = {};

  // Collect BOMs and index primary components
  const files = listJson(CX_DIR);
  const entries = [];
  const uriToNode = {};

  function stripUrn(u) {
    if (typeof u !== 'string') return u;
    const s = u.trim();
    return s.startsWith('urn:mlmd-bom-ref:') ? s.slice('urn:mlmd-bom-ref:'.length) : s;
  }
  function addUriMap(uri, nodeId) { if (uri && typeof uri === 'string') uriToNode[uri] = nodeId; }

  // Pass 1: nodes and URI mapping
  for (const fp of files) {
    const bom = readJson(fp); if (!bom) continue;
    const rel = relFromView(fp);
    const metaComp = (bom.metadata || {}).component || null;
    const comps = (bom.components || []);
    let primary = null;
    // Prefer metadata.component, else first component with type application/data/file
    if (metaComp && (metaComp.type === 'application' || metaComp.type === 'data' || metaComp.type === 'file')) primary = metaComp;
    if (!primary) {
      for (const c of comps) { if (c.type === 'application' || c.type === 'data' || c.type === 'file') { primary = c; break; } }
    }
    if (!primary) continue;

    const kind = primary.type === 'application' ? 'model' : 'dataset';
    const name = primary.name || 'unknown';
    const version = primary.version || '';
    const nodeId = safeNodeId(kind === 'model' ? 'model' : 'data', name, version);

    // Node creation
    if (!g.nodes[nodeId]) {
      if (kind === 'model') {
        g.nodes[nodeId] = { id: nodeId, label: `${name}\n${version}`, color: '#1976d2', shape: 'dot', size: 18 };
      } else {
        g.nodes[nodeId] = { id: nodeId, label: `${name}\n${version}`, color: '#2e7d32', shape: 'dot', size: 16 };
      }
    }
    details[nodeId] = details[nodeId] || {}; details[nodeId].cx = primary; details[nodeId].cx_file = rel;

    // Map logical self URIs
    if (kind === 'model') {
      const nm = String(name);
      addUriMap(`models://${nm.toLowerCase()}/${version}`, nodeId);
      addUriMap(`models://${nm}/${version}`, nodeId);
      if (primary['bom-ref'] && String(primary['bom-ref']).startsWith('models://')) addUriMap(String(primary['bom-ref']), nodeId);
    } else {
      // dataset: also include split suffix if present
      const nm = String(name);
      const lower = nm.toLowerCase();
      const baseLower = `data://${lower}/${version}`;
      const baseExact = `data://${nm}/${version}`;
      // Heuristic: strip '-dataset' suffix so 'data://churn/...' also resolves
      const altLowerName = lower.endsWith('-dataset') ? lower.slice(0, -9) : lower;
      const altExactName = nm.endsWith('-dataset') ? nm.slice(0, -9) : nm;
      const altLower = `data://${altLowerName}/${version}`;
      const altExact = `data://${altExactName}/${version}`;
      addUriMap(baseLower, nodeId);
      addUriMap(baseExact, nodeId);
      if (altLower !== baseLower) addUriMap(altLower, nodeId);
      if (altExact !== baseExact) addUriMap(altExact, nodeId);
      let splitVal = null;
      if (Array.isArray(primary.properties)) {
        for (const p of primary.properties) { if ((p.name === 'ml:split' || p.name === 'split') && typeof p.value === 'string' && p.value) { splitVal = p.value; break; } }
      }
      if (splitVal) {
        addUriMap(`${baseLower}/${splitVal}`, nodeId);
        addUriMap(`${baseExact}/${splitVal}`, nodeId);
        if (altLower !== baseLower) addUriMap(`${altLower}/${splitVal}`, nodeId);
        if (altExact !== baseExact) addUriMap(`${altExact}/${splitVal}`, nodeId);
      } else {
        // Also map a common default split path so references with '/train' still resolve when split missing in props
        addUriMap(`${baseLower}/train`, nodeId);
        addUriMap(`${baseExact}/train`, nodeId);
        if (altLower !== baseLower) addUriMap(`${altLower}/train`, nodeId);
        if (altExact !== baseExact) addUriMap(`${altExact}/train`, nodeId);
      }
      if (primary['bom-ref'] && String(primary['bom-ref']).startsWith('data://')) addUriMap(String(primary['bom-ref']), nodeId);
    }

    // Store entry for pass 2
    entries.push({ fp, rel, kind, nodeId, name, version, primary, bom });
  }

  // Pass 2: edges (dependencies, lineage, and model↔dataset) using only ExternalReferences
  const edgeKeys = new Set();
  function addEdge(from, to, opts) {
    const key = `${from}→${to}|${opts.title || ''}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    g.edges.push({ from, to, ...opts });
  }

  for (const e of entries) {
    const { bom, primary, nodeId } = e;
    const comps = (bom.components || []);
    const byRef = {};
    for (const c of comps) { if (c['bom-ref']) byRef[c['bom-ref']] = c; }

    // Dependencies (libraries) from dependency graph, only for models
    if (e.kind === 'model') {
      const rootRef = primary['bom-ref'];
      const depRefs = new Set();
      for (const dep of (bom.dependencies || [])) { if (dep.ref === rootRef) { for (const d of (dep.dependsOn || [])) depRefs.add(d); } }
      for (const r of depRefs) {
        const c = byRef[r] || {};
        const name = c.name || r;
        const version = c.version;
        const libId = safeNodeId('lib', name, version);
        if (!g.nodes[libId]) g.nodes[libId] = { id: libId, label: `${name}\n${version || ''}`, color: '#616161', shape: 'box', size: 12 };
        if (c && Object.keys(c).length) { details[libId] = details[libId] || {}; details[libId].cx = c; details[libId].cx_file = e.rel; }
        addEdge(nodeId, libId, { color: '#90a4ae', arrows: 'to', title: 'depends_on' });
      }
    }

    // ExternalReferences for lineage and model↔dataset
    for (const er of (primary.externalReferences || [])) {
      if (!er || er.type !== 'bom' || !er.url) continue;
      let target = stripUrn(er.url);
      const comment = String(er.comment || '').toLowerCase();
      if (!target) continue;

      // Model lineage
      if (e.kind === 'model' && target.startsWith('models://')) {
        const targetId = uriToNode[target] || uriToNode[target.toLowerCase()]; if (!targetId) continue;
        if (comment.includes('parent') && comment.includes('model')) { // owner is child
          addEdge(targetId, nodeId, { color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
        } else if (comment.includes('child') && comment.includes('model')) { // owner is parent
          addEdge(nodeId, targetId, { color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
        }
        continue;
      }

      // Dataset lineage
      if (e.kind === 'dataset' && target.startsWith('data://')) {
        // try exact, then strip split, then strip '-dataset'
        const t0 = uriToNode[target];
        const tParts = target.split('/');
        const tNoSplit = tParts.length >= 5 ? tParts.slice(0, 4).join('/') : null;
        const namePart = tParts[2] || '';
        const versionPart = tParts[3] || '';
        const altName = namePart.endsWith('-dataset') ? namePart.slice(0, -9) : (namePart + '-dataset');
        const tAlt = `data://${altName}/${versionPart}`;
        const tAltSplit = `${tAlt}/train`;
        const targetId = t0 || (tNoSplit && uriToNode[tNoSplit]) || uriToNode[tAlt] || uriToNode[tAltSplit];
        if (!targetId) { log('debug', 'unresolved dataset lineage target', { target, tNoSplit, tAlt, tAltSplit }); continue; }
        if (comment.includes('parent') && comment.includes('dataset')) { // owner is child
          addEdge(targetId, nodeId, { color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
        } else if (comment.includes('child') && comment.includes('dataset')) { // owner is parent
          addEdge(nodeId, targetId, { color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
        }
        continue;
      }

      // Model ↔ Dataset usage
      if (target.startsWith('data://')) {
        const dsId = uriToNode[target] || uriToNode[target.split('/').slice(0, 4).join('/')] || uriToNode[target.toLowerCase()]; if (!dsId) continue;
        if (e.kind === 'model' && comment.includes('uses dataset')) {
          addEdge(nodeId, dsId, { color: '#c62828', arrows: 'to', title: 'uses_dataset' });
        }
        continue;
      }
      if (target.startsWith('models://')) {
        const mId = uriToNode[target] || uriToNode[target.toLowerCase()]; if (!mId) continue;
        if (e.kind === 'dataset' && comment.includes('used by model')) {
          addEdge(mId, nodeId, { color: '#c62828', arrows: 'to', title: 'uses_dataset' });
        }
        continue;
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
      <div class="links">Click a model to open full BOM(s).</div>
  <h4>CycloneDX</h4><pre id="cxJson">Select a node...</pre>
  <div class="links" id="bomLinks"></div>
    </div>
  </div>
  <script>
    const DATA = ${JSON.stringify(data)};
    const container = document.getElementById('graph');
    // Enable vis-network physics for automatic layout
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
        // Only show the CycloneDX link for model or dataset nodes
        if((id.startsWith('model:') || id.startsWith('data:')) && d.cx_file)
          links.push('<a target="_blank" href="'+('/output/'+d.cx_file)+'">Open CycloneDX</a>');
        bl.innerHTML = links.join(' ');
      }
    }
    network.on('selectNode', p=>{ if(p.nodes && p.nodes.length) showDetails(p.nodes[0]); });
    network.on('doubleClick', p=>{ if(p.nodes && p.nodes.length){ const id=p.nodes[0]; if(id && id.startsWith('model:')){ const d=(DATA.details||{})[id]||{}; if(d.cx_file) window.open('/output/'+d.cx_file,'_blank'); if(d.spdx_file) window.open('/output/'+d.spdx_file,'_blank'); } }});
  </script>
</body>
</html>`;
}

let cache = { html: '' };
function rebuild() {
  const t0 = Date.now();
  try {
    const { g, details } = buildGraph();
    // Log a brief summary of edge types for quick diagnostics
    try {
      const summary = {};
      for (const e of g.edges) {
        const k = e.title || 'unknown';
        summary[k] = (summary[k] || 0) + 1;
      }
      log('info', 'edge summary', summary);
    } catch { }
    cache.html = makeHtml({ g, details });
    const elapsed = Date.now() - t0;
    log('info', 'rebuilt graph', { nodes: Object.keys(g.nodes).length, edges: g.edges.length, ms: elapsed });
  } catch (e) {
    log('error', 'rebuild failed', { error: String(e) });
  }
}

// Initial build if present
rebuild();

// File watchers
const watcher = chokidar.watch([CX_DIR], { ignoreInitial: true, depth: 1 });
watcher.on('add', (p) => { log('debug', 'file added', { file: relFromView(p) }); rebuild(); })
  .on('change', (p) => { log('debug', 'file changed', { file: relFromView(p) }); rebuild(); })
  .on('unlink', (p) => { log('debug', 'file removed', { file: relFromView(p) }); rebuild(); })
  .on('error', (e) => { log('error', 'watch error', { error: String(e) }); });

// Routes
// Request logging middleware
let REQ_ID = 0;
app.use((req, res, next) => {
  const id = ++REQ_ID; const start = Date.now();
  log('info', 'request', { id, method: req.method, path: req.originalUrl });
  res.on('finish', () => { log('info', 'response', { id, status: res.statusCode, ms: Date.now() - start }); });
  next();
});

app.get('/', (req, res) => { if (!cache.html) rebuild(); res.set('Cache-Control', 'no-store'); return res.send(cache.html); });
app.use('/output', express.static(OUTPUT_ROOT, { etag: false, lastModified: false, cacheControl: false, setHeaders: res => { res.set('Cache-Control', 'no-store'); } }));
// Serve vis-network assets from node_modules
app.get('/assets/vis-network.min.js', (req, res) => {
  const jsPath = firstExisting([
    path.join(VIS_PKG, 'dist', 'vis-network.min.js'),
  ]);
  if (!jsPath) return res.status(404).send('vis-network js not found');
  res.type('application/javascript');
  return res.sendFile(jsPath);
});
app.get('/assets/vis-network.min.css', (req, res) => {
  const cssPath = firstExisting([
    path.join(VIS_PKG, 'styles', 'vis-network.min.css'),
    path.join(VIS_PKG, 'dist', 'styles', 'vis-network.min.css'),
  ]);
  if (!cssPath) return res.status(404).send('vis-network css not found');
  res.type('text/css');
  return res.sendFile(cssPath);
});

// (No generic /static route; vis assets are served via /assets/* directly from node_modules)

// Error handler
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => { log('error', 'unhandled error', { error: String(err) }); res.status(500).send('Internal Server Error'); });

process.on('uncaughtException', (e) => { log('error', 'uncaughtException', { error: String(e) }); });
process.on('unhandledRejection', (e) => { log('error', 'unhandledRejection', { error: String(e) }); });

app.listen(PORT, () => { log('info', 'viewer server running', { url: `http://localhost:${PORT}`, port: Number(PORT) }); });
