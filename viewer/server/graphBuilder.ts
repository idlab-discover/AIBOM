import path from 'node:path';
import fs from 'node:fs';

export function listJson(dir: string): string[] {
  try { return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => path.join(dir, f)); } catch { return []; }
}
export function readJson(p: string): any | null { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } }

export function buildGraph(outputRoot: string) {
  const cxDir = path.join(outputRoot, 'cyclonedx');
  function edgeExists(edges: any[], from: string, to: string, title: string) {
    return edges.some(e => e.from === from && e.to === to && e.title === title);
  }
  const g: { nodes: Record<string, any>, edges: any[] } = { nodes: {}, edges: [] };
  const details: Record<string, any> = {};
  const files = listJson(cxDir);
  const bomRefToNode: Record<string, string> = {};
  const entries: Array<any> = [];
  const relFromView = (p: string) => path.relative(outputRoot, p).split(path.sep).join('/');

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
    for (const er of (metaComp.externalReferences || [])) {
      if (!er || er.type !== 'bom' || !er.url) continue;
      let targetRef = String(er.url).startsWith('urn:mlmd-bom-ref:') ? String(er.url).slice('urn:mlmd-bom-ref:'.length) : String(er.url);
      if (!bomRefToNode[targetRef]) continue;
      const comment = String(er.comment || '').toLowerCase();
      if (kind === 'model' && comment.includes('parent') && comment.includes('model')) {
        if (!edgeExists(g.edges, bomRefToNode[targetRef], nodeId, 'model_lineage')) {
          g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
        }
      } else if (kind === 'model' && comment.includes('child') && comment.includes('model')) {
        if (!edgeExists(g.edges, nodeId, bomRefToNode[targetRef], 'model_lineage')) {
          g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#f57c00', dashes: true, arrows: 'to', title: 'model_lineage' });
        }
      } else if (kind === 'dataset' && comment.includes('parent') && comment.includes('dataset')) {
        if (!edgeExists(g.edges, bomRefToNode[targetRef], nodeId, 'dataset_lineage')) {
          g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
        }
      } else if (kind === 'dataset' && comment.includes('child') && comment.includes('dataset')) {
        if (!edgeExists(g.edges, nodeId, bomRefToNode[targetRef], 'dataset_lineage')) {
          g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#f57c00', dashes: true, arrows: 'to', title: 'dataset_lineage' });
        }
      } else if (kind === 'model' && comment.includes('uses dataset')) {
        if (!edgeExists(g.edges, nodeId, bomRefToNode[targetRef], 'uses_dataset')) {
          g.edges.push({ from: nodeId, to: bomRefToNode[targetRef], color: '#c62828', arrows: 'to', title: 'uses_dataset' });
        }
      } else if (kind === 'dataset' && comment.includes('used by model')) {
        if (!edgeExists(g.edges, bomRefToNode[targetRef], nodeId, 'uses_dataset')) {
          g.edges.push({ from: bomRefToNode[targetRef], to: nodeId, color: '#c62828', arrows: 'to', title: 'uses_dataset' });
        }
      }
    }
    if (kind === 'model' && Array.isArray(bom.dependencies)) {
      const modelDep = bom.dependencies.find((dep: any) => dep.ref === nodeId);
      if (modelDep && Array.isArray(modelDep.dependsOn)) {
        const byRef: Record<string, any> = {};
        for (const c of (bom.components || [])) {
          if (c['bom-ref']) byRef[c['bom-ref']] = c;
        }
        for (const depRef of modelDep.dependsOn) {
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
  const nodes = Object.values(g.nodes);
  const edges = g.edges;
  return { nodes, edges, details };
}
