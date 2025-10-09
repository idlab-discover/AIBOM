#!/usr/bin/env node
// Minimal live viewer server: watches /app/output/{cyclonedx,spdx}, rebuilds in-memory graph, serves HTML and JSON endpoints.
import express from 'express';
import path from 'path';
import fs from 'fs';
import chokidar from 'chokidar';

const OUTPUT_ROOT = '/app/output';
const CX_DIR = path.join(OUTPUT_ROOT, 'cyclonedx');
const SPDX_DIR = path.join(OUTPUT_ROOT, 'spdx');

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

function readJson(p){ try { return JSON.parse(fs.readFileSync(p,'utf8')); } catch (e) { log('debug','failed to parse json',{ file:p, error:String(e)}); return null; } }
function listJson(dir){ try { return fs.readdirSync(dir).filter(f=>f.endsWith('.json')).map(f=>path.join(dir,f)); } catch { return []; } }
function safeNodeId(prefix, name, version){ const n=(name||'unknown').trim(); const v=(version||'').trim(); return v?`${prefix}:${n}@${v}`:`${prefix}:${n}`; }
function relFromView(p){ return path.relative(OUTPUT_ROOT, p); }

function buildGraph(){
  const g = { nodes:{}, edges:[] };
  const details = {};
  // CycloneDX
  const bomToModel = {};
  for(const fp of listJson(CX_DIR)){
    const bom = readJson(fp); if(!bom) continue;
    let serial = bom.serialNumber; const bomVersion = bom.version || 1;
    // Normalize serial to not have double 'urn:'
    if(serial && serial.startsWith('urn:')) serial = serial.slice(4);
    let model = (bom.metadata||{}).component || null;
    if(!model || model.type !== 'application'){
      for(const c of (bom.components||[])) if(c.type==='application'){ model=c; break; }
    }
    if(!model) continue;
    const modelId = safeNodeId('model', model.name, model.version);
    const ref = model['bom-ref'];
    if(serial && ref){ bomToModel[`urn:cdx:${serial}/${bomVersion}#${ref}`]=modelId; }
  }
  for(const fp of listJson(CX_DIR)){
    const bom = readJson(fp); if(!bom) continue;
    let model = (bom.metadata||{}).component || null;
    if(!model || model.type !== 'application'){
      for(const c of (bom.components||[])) if(c.type==='application'){ model=c; break; }
    }
    if(!model) continue;
    const modelId = safeNodeId('model', model.name, model.version);
    if(!g.nodes[modelId]) g.nodes[modelId] = { id:modelId, label:`${model.name}\n${model.version||''}`, color:'#1976d2', shape:'dot', size:18 };
    const rel = relFromView(fp);
    details[modelId] = details[modelId] || {}; details[modelId].cx = model; details[modelId].cx_file = rel;
    const byRef={}; for(const c of (bom.components||[])){ if(c['bom-ref']) byRef[c['bom-ref']]=c; }
    const modelRef = model['bom-ref']; const depRefs=new Set();
    for(const dep of (bom.dependencies||[])) if(dep.ref===modelRef){ for(const d of (dep.dependsOn||[])) depRefs.add(d); }
    for(const r of depRefs){
      const c = byRef[r] || {}; const name = c.name || r; const version = c.version; const isData = (typeof r==='string') && r.startsWith('data://');
      const libId = safeNodeId('lib', name, version); const dataId = safeNodeId('data', name, version);
      const depId = g.nodes[dataId] ? dataId : (g.nodes[libId] ? libId : (isData ? dataId : libId));
      if(!g.nodes[depId]) g.nodes[depId] = { id:depId, label:`${name}\n${version||''}`, color: depId.startsWith('data:')?'#2e7d32':'#616161', shape:'box', size:12 };
      if(c && Object.keys(c).length){ details[depId]=details[depId]||{}; details[depId].cx=c; details[depId].cx_file=rel; }
      g.edges.push({ from:modelId, to:depId, color:'#90a4ae', arrows:'to', title:'depends_on' });
    }
    for(const er of (model.externalReferences||[])) if(er.type==='bom'){
      let url = er.url;
      // Normalize url to not have double 'urn:'
      if(url.startsWith('urn:cdx:urn:')) url = 'urn:cdx:' + url.slice(12);
      let pid = bomToModel[url];
      if(!pid){
        // Try to match by stripping 'urn:cdx:' prefix if present
        const urlNorm = url.startsWith('urn:cdx:') ? url.slice(8) : url;
        for(const k of Object.keys(bomToModel)){
          const kNorm = k.startsWith('urn:cdx:') ? k.slice(8) : k;
          if(urlNorm === kNorm){ pid = bomToModel[k]; break; }
        }
      }
      if(pid){
        g.edges.push({ from:pid, to:modelId, color:'#f57c00', dashes:true, arrows:'to', title:'lineage:parent→child' });
      }
    }
  }
  // SPDX
  const nsToModel = {};
  for(const fp of listJson(SPDX_DIR)){
    const doc = readJson(fp); if(!doc) continue;
    const ns = doc.documentNamespace; let model = null;
    for(const el of (doc.elements||[])) if(el.type==='Package' && el.id==='SPDXRef-Model'){ model=el; break; }
    if(ns && model){ nsToModel[ns] = safeNodeId('model', model.name, model.version); }
  }
  for(const fp of listJson(SPDX_DIR)){
    const doc = readJson(fp); if(!doc) continue;
    const packages = {}; for(const el of (doc.elements||[])) if(el.type==='Package'){ packages[el.id]=el; }
    const model = packages['SPDXRef-Model']; if(!model) continue;
    const modelId = safeNodeId('model', model.name, model.version);
    if(!g.nodes[modelId]) g.nodes[modelId] = { id:modelId, label:`${model.name}\n${model.version||''}`, color:'#1976d2', shape:'dot', size:18 };
    const rel = relFromView(fp); details[modelId]=details[modelId]||{}; details[modelId].spdx=model; details[modelId].spdx_file=rel;
    for(const el of (doc.elements||[])){
      if(el.type!=='Relationship') continue;
      const rt = el.relationshipType;
      if(rt==='dependsOn' && el.from==='doc:SPDXRef-Model'){
        const toId=(el.to||'').split(':',1).pop(); const dep=packages[toId]; if(!dep) continue;
        const name=dep.name; const version=dep.version; const isData=(name||'').toLowerCase().includes('dataset');
        const libId=safeNodeId('lib',name,version); const dataId=safeNodeId('data',name,version); const depId = g.nodes[dataId]?dataId:(g.nodes[libId]?libId:(isData?dataId:libId));
        if(!g.nodes[depId]) g.nodes[depId] = { id:depId, label:`${name}\n${version||''}`, color: depId.startsWith('data:')?'#2e7d32':'#616161', shape:'box', size:12 };
        details[depId]=details[depId]||{}; details[depId].spdx=dep; details[depId].spdx_file=rel;
        g.edges.push({ from:modelId, to:depId, color:'#90a4ae', arrows:'to', title:'depends_on' });
      } else if(rt==='descendantOf' && el.from==='doc:SPDXRef-Model'){
        const toTarget=el.to||''; let parentNs=null; for(const m of (doc.externalMaps||[])) if(m.externalDocumentId===toTarget.split(':',1)[0]){ parentNs=m.documentNamespace; break; }
        const pid = parentNs ? nsToModel[parentNs] : null; if(pid){ g.edges.push({ from:pid, to:modelId, color:'#f57c00', dashes:true, arrows:'to', title:'lineage:parent→child' }); }
      }
    }
    // Attach SPDX package json to existing nodes by name/version
    for(const [pid,pkg] of Object.entries(packages)){
      if(pid==='SPDXRef-Model') continue; const name=pkg.name; const version=pkg.version;
      const libId=safeNodeId('lib',name,version); const dataId=safeNodeId('data',name,version); const existing = g.nodes[dataId]?dataId:(g.nodes[libId]?libId:null);
      if(existing){ details[existing]=details[existing]||{}; details[existing].spdx=pkg; details[existing].spdx_file=rel; }
    }
  }
  return {g, details};
}

function applyPositions(g){
  const pos={}; const modelNodes=Object.keys(g.nodes).filter(n=>n.startsWith('model:'));
  const groups={}; for(const n of modelNodes){ const [name,ver]=n.split(':')[1].split('@').length>1? [n.split(':')[1].split('@')[0], n.split('@').pop()] : [n.split(':')[1], '']; (groups[name]||(groups[name]=[])).push({n,ver}); }
  const X_SP=600, Y_SP=280; const cols=Object.keys(groups).sort();
  for(let ci=0; ci<cols.length; ci++){ const name=cols[ci]; const chain=groups[name]; chain.sort((a,b)=> (a.ver||'').localeCompare(b.ver||''));
    for(let ri=0; ri<chain.length; ri++){ const node=chain[ri].n; pos[node]={x:ci*X_SP, y:ri*Y_SP}; }
  }
  const depToModels={}; for(const e of g.edges){ if(e.title==='depends_on' && String(e.from).startsWith('model:')){ (depToModels[e.to]||(depToModels[e.to]=[])).push(e.from); } }
  for(const [dep,models] of Object.entries(depToModels)){
    if(models.length===1){ const m=models[0]; const c=pos[m]; if(!c) continue; const deps=g.edges.filter(e=>e.from===m && e.title==='depends_on').map(e=>e.to).filter(d=> (depToModels[d]||[]).length===1); const idx=deps.indexOf(dep); const R=160+10*deps.length; const angle=2*Math.PI*(idx/Math.max(1,deps.length)); pos[dep]={ x:c.x+R*Math.cos(angle), y:c.y+R*Math.sin(angle) }; }
    else { let sx=0,sy=0,cnt=0; for(const m of models){ const p=pos[m]; if(p){ sx+=p.x; sy+=p.y; cnt++; } } if(cnt) pos[dep]={ x:sx/cnt, y:sy/cnt }; }
  }
  return pos;
}

function makeHtml({g,details}){
  const pos = applyPositions(g);
  const nodes = Object.values(g.nodes).map(n=>{ const p=pos[n.id]; return p? {...n, x:p.x, y:p.y } : n; });
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
    #graph { flex: 0 0 62vw; height: 100vh; }
    #panel { flex: 1; border-left: 1px solid #ddd; background:#fafafa; padding:10px; overflow:auto; }
    pre { background:#fff; border:1px solid #eee; padding:8px; white-space:pre-wrap; }
    .links a{ margin-right:8px; }
  </style>
  <script src="https://unpkg.com/vis-network@9.1.6/dist/vis-network.min.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/vis-network@9.1.6/styles/vis-network.min.css"/>
</head>
<body>
  <div id="container">
    <div id="graph"></div>
    <div id="panel">
      <h3>Details</h3>
      <div class="links">Click a model to open full BOM(s).</div>
      <h4>CycloneDX</h4><pre id="cxJson">Select a node...</pre>
      <h4>SPDX</h4><pre id="spdxJson"></pre>
      <div class="links" id="bomLinks"></div>
    </div>
  </div>
  <script>
    const DATA = ${JSON.stringify(data)};
    const container = document.getElementById('graph');
    const network = new vis.Network(container, { nodes: new vis.DataSet(DATA.nodes), edges: new vis.DataSet(DATA.edges) }, { interaction:{ hover:true, dragNodes:true }, physics:false, edges:{ smooth:{ type:'dynamic' } } });
  function showDetails(id){ const d=(DATA.details||{})[id]||{}; var cxEl=document.getElementById('cxJson'); if(cxEl) cxEl.textContent=d.cx? JSON.stringify(d.cx,null,2):'N/A'; var sEl=document.getElementById('spdxJson'); if(sEl) sEl.textContent=d.spdx? JSON.stringify(d.spdx,null,2): 'N/A'; var bl=document.getElementById('bomLinks'); if(bl){ var links=[]; if(d.cx_file) links.push('<a target="_blank" href="'+('/output/'+d.cx_file)+'">Open CycloneDX</a>'); if(d.spdx_file) links.push('<a target="_blank" href="'+('/output/'+d.spdx_file)+'">Open SPDX</a>'); bl.innerHTML=links.join(' ');} }
  network.on('selectNode', p=>{ if(p.nodes && p.nodes.length) showDetails(p.nodes[0]); });
  network.on('doubleClick', p=>{ if(p.nodes && p.nodes.length){ const id=p.nodes[0]; if(id && id.startsWith('model:')){ const d=(DATA.details||{})[id]||{}; if(d.cx_file) window.open('/output/'+d.cx_file,'_blank'); if(d.spdx_file) window.open('/output/'+d.spdx_file,'_blank'); } }});
  </script>
</body>
</html>`;
}

let cache = { html: '' };
function rebuild(){
  const t0 = Date.now();
  try {
    const {g,details} = buildGraph();
    cache.html = makeHtml({g,details});
    const elapsed = Date.now()-t0;
    log('info','rebuilt graph', { nodes: Object.keys(g.nodes).length, edges: g.edges.length, ms: elapsed });
  } catch (e) {
    log('error','rebuild failed', { error: String(e) });
  }
}

// Initial build if present
rebuild();

// File watchers
const watcher = chokidar.watch([CX_DIR, SPDX_DIR], { ignoreInitial: true, depth: 1 });
watcher.on('add', (p)=>{ log('debug','file added', { file: relFromView(p) }); rebuild(); })
  .on('change', (p)=>{ log('debug','file changed', { file: relFromView(p) }); rebuild(); })
  .on('unlink', (p)=>{ log('debug','file removed', { file: relFromView(p) }); rebuild(); })
  .on('error', (e)=>{ log('error','watch error', { error: String(e) }); });

// Routes
// Request logging middleware
let REQ_ID = 0;
app.use((req,res,next)=>{
  const id = ++REQ_ID; const start = Date.now();
  log('info','request', { id, method:req.method, path:req.originalUrl });
  res.on('finish', ()=>{ log('info','response', { id, status: res.statusCode, ms: Date.now()-start }); });
  next();
});

app.get('/', (req,res)=>{ if(!cache.html) rebuild(); res.set('Cache-Control','no-store'); return res.send(cache.html); });
app.use('/output', express.static(OUTPUT_ROOT, { etag:false, lastModified:false, cacheControl:false, setHeaders:res=>{ res.set('Cache-Control','no-store'); } }));

// Error handler
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next)=>{ log('error','unhandled error', { error:String(err) }); res.status(500).send('Internal Server Error'); });

process.on('uncaughtException', (e)=>{ log('error','uncaughtException', { error: String(e) }); });
process.on('unhandledRejection', (e)=>{ log('error','unhandledRejection', { error: String(e) }); });

app.listen(PORT, ()=>{ log('info', 'viewer server running', { url: `http://localhost:${PORT}`, port: Number(PORT) }); });
