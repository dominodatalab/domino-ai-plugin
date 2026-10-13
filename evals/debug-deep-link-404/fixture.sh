#!/usr/bin/env bash
set -euo pipefail
cat > vite.config.js <<'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: { host: '0.0.0.0', port: 8888, strictPort: true },
})
EOF
cat > app.sh <<'EOF'
#!/bin/bash
set -e
cd /mnt/code
npm ci
npm run build
npx serve dist -l 8888
EOF
cat > package.json <<'EOF'
{ "name": "reports-ui", "private": true, "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "19.3.0", "react-dom": "19.3.0", "react-router-dom": "7.18.4", "serve": "^14.2.6" },
  "devDependencies": { "vite": "^8.3.0", "@vitejs/plugin-react": "^6.1.0" } }
EOF
