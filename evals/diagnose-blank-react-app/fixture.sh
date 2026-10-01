#!/usr/bin/env bash
set -euo pipefail
cat > vite.config.js <<'JS'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 3000 },
})
JS
cat > app.sh <<'SH'
#!/bin/bash
set -e
cd /mnt/code
npm ci
npx serve dist -l 3000
SH
cat > package.json <<'PKG'
{ "name": "dash-ui", "private": true, "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "18.2.0", "react-dom": "18.2.0", "serve": "^14.2.0" },
  "devDependencies": { "vite": "^5.4.0", "@vitejs/plugin-react": "^4.3.4" } }
PKG
