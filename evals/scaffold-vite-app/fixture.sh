#!/usr/bin/env bash
# A fresh Vite React project, as `npm create vite@latest web -- --template react` leaves it (trimmed).
set -euo pipefail
cat > package.json <<'EOF'
{
  "name": "sales-dashboard",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" },
  "dependencies": { "react": "^19.2.0", "react-dom": "^19.2.0" },
  "devDependencies": { "@vitejs/plugin-react": "^6.0.0", "vite": "^8.0.0" }
}
EOF
cat > vite.config.js <<'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
EOF
cat > index.html <<'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Sales dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF
mkdir -p src
cat > src/main.jsx <<'EOF'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
EOF
cat > src/App.jsx <<'EOF'
export default function App() {
  return <h1>Sales dashboard</h1>
}
EOF
cat > .gitignore <<'EOF'
node_modules
dist
EOF
