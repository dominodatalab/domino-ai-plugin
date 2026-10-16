// server.js: serves the build app.sh selected (BUILD_DIR) and makes Domino calls server-side, so tokens
// never reach the browser. Node built-ins only (Node 18 or later): the App starts without npm.
// Requires "type": "module" in package.json (the Vite scaffold sets it).
import http from 'node:http'
import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import path from 'node:path'

const dist = path.resolve(process.env.BUILD_DIR || 'build')
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.map': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.txt': 'text/plain',
}

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body))
}

async function readJson(req, limit = 1_000_000) {
  let body = ''
  for await (const chunk of req) {
    body += chunk
    if (body.length > limit) throw Object.assign(new Error('request too large'), { status: 413 })
  }
  try {
    return JSON.parse(body || '{}')
  } catch {
    throw Object.assign(new Error('request body is not JSON'), { status: 400 })
  }
}

// POST api/predict -> Domino endpoint, with MODEL_API_URL and MODEL_API_TOKEN from Project environment
// variables. Synchronous endpoints take HTTP Basic with the token as user and password; asynchronous
// endpoints take "Authorization: Bearer <token>" instead.
async function predict(req, res) {
  const url = process.env.MODEL_API_URL
  const token = process.env.MODEL_API_TOKEN
  if (!url || !token) return json(res, 503, { error: 'MODEL_API_URL or MODEL_API_TOKEN is not set' })
  const data = await readJson(req)
  const upstream = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Basic ' + Buffer.from(token + ':' + token).toString('base64') },
    body: JSON.stringify({ data }),
  })
  res.writeHead(upstream.status, { 'Content-Type': 'application/json' }).end(await upstream.text())
}

// GET api/projects -> the Domino API as the viewer: forward the request's token. Never retry without it:
// $DOMINO_API_HOST runs a call without Authorization as the publisher. Most routes accept the viewer's
// token only when the App version has extended identity propagation.
async function projects(req, res) {
  const auth = req.headers.authorization
  if (!auth?.startsWith('Bearer ') || !auth.slice(7).trim()) return json(res, 401, { error: 'no viewer token' })
  const upstream = await fetch(process.env.DOMINO_API_HOST + '/api/projects/beta/projects?limit=20', {
    headers: { Authorization: auth },
  })
  res.writeHead(upstream.status, { 'Content-Type': 'application/json' }).end(await upstream.text())
}

// Files from the build; extension-less paths fall back to index.html, a missing asset stays a 404.
async function serveFile(req, res, route) {
  const file0 = path.join(dist, route)
  if (file0 !== dist && !file0.startsWith(dist + path.sep)) return res.writeHead(404).end()
  let file = file0
  let info = await stat(file).catch(() => null)
  if (info?.isDirectory()) {
    file = path.join(file, 'index.html')
    info = await stat(file).catch(() => null)
  }
  if (!info) {
    if (path.extname(file)) return res.writeHead(404).end()
    file = path.join(dist, 'index.html')
  }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' })
  createReadStream(file).on('error', () => res.destroy()).pipe(res)
}

http.createServer(async (req, res) => {
  try {
    const route = decodeURIComponent(new URL(req.url, 'http://app').pathname)
    if (route === '/healthz') return json(res, 200, { status: 'ok', build: process.env.APP_BUILD || null })
    if (req.method === 'POST' && route === '/api/predict') return await predict(req, res)
    if (req.method === 'GET' && route === '/api/projects') return await projects(req, res)
    if (req.method !== 'GET' && req.method !== 'HEAD') return res.writeHead(405).end()
    await serveFile(req, res, route)
  } catch (err) {
    console.error(req.method, req.url, err.message)
    if (!res.headersSent) json(res, err.status || 502, { error: err.status ? err.message : 'upstream call failed' })
  }
}).listen(8888, '0.0.0.0', () => console.log(`serving ${dist} on 0.0.0.0:8888`))   // Domino requires 0.0.0.0:8888
