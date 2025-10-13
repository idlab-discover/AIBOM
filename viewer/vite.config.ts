import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { buildGraph, listJson, readJson } from './server/graphBuilder.js'


const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

function graphApiPlugin(): Plugin {
  const outputRoot = path.resolve(__dirname, '..', 'output')
  function staticHandler(req: IncomingMessage, res: ServerResponse, next: () => void) {
    try {
      const url = req.url || '/'
      const rel = url.replace(/^\/output\/?/, '')
      const fp = path.join(outputRoot, rel)
      if (fs.existsSync(fp) && fs.statSync(fp).isFile()) {
        res.setHeader('Cache-Control', 'no-store')
        const ext = path.extname(fp).toLowerCase()
        const type = ext === '.json' ? 'application/json' : ext === '.txt' ? 'text/plain' : 'application/octet-stream'
        res.setHeader('Content-Type', type)
        const buf = fs.readFileSync(fp)
        res.end(buf)
        return
      }
    } catch (e) {
      // fall through
    }
    next()
  }
  return {
    name: 'mlmd-graph-api',
    configureServer(server) {
      server.middlewares.use('/api/cx-graph', (_req: IncomingMessage, res: ServerResponse) => {
        try {
          const data = buildGraph(outputRoot)
          res.setHeader('Cache-Control', 'no-store')
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(data))
        } catch (e: any) {
          res.statusCode = 500
          res.end(JSON.stringify({ error: String(e?.message || e) }))
        }
      })
      server.middlewares.use('/output', staticHandler as any)
    },
    configurePreviewServer(server) {
      server.middlewares.use('/api/cx-graph', (_req: IncomingMessage, res: ServerResponse) => {
        try {
          const data = buildGraph(outputRoot)
          res.setHeader('Cache-Control', 'no-store')
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(data))
        } catch (e: any) {
          res.statusCode = 500
          res.end(JSON.stringify({ error: String(e?.message || e) }))
        }
      })
      server.middlewares.use('/output', staticHandler as any)
    },
  }
}

export default defineConfig({
  plugins: [react(), graphApiPlugin()],
  server: {
    fs: { allow: [path.resolve(__dirname, '..')] },
    port: 5173,
    strictPort: false,
  },
  preview: {
    port: 5173,
    strictPort: false,
  },
})
