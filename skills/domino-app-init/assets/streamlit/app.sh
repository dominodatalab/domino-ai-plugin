#!/bin/bash
# Domino App entry point for a Streamlit application.
# Domino runs this file when the App starts; Streamlit must listen on 0.0.0.0:8888
# (its default is 8501).

set -e

echo "=== Domino Streamlit App ==="
echo "Project: $DOMINO_PROJECT_NAME"
echo "Owner: $DOMINO_PROJECT_OWNER"
echo "Started by: $DOMINO_STARTING_USERNAME"

# Run from the directory that holds this script and app.py (the repo root, or the app
# subfolder when app.sh lives there).
cd "$(dirname "$0")"

# Streamlit must be in the Compute Environment (packages pip-installed in a Workspace are not in
# the App). Preferred: an environment that includes it, or requirements.txt at the project root.
# Prototype only (slower start, needs PyPI egress): uncomment the next line and change the last
# line to `exec python -m streamlit run app.py --server.port 8888 --server.address 0.0.0.0`.
# python -m pip install --user -q streamlit

# enableCORS and enableXsrfProtection are off (Domino's Streamlit example sets the same);
# keep them unless your deployment is known to work with the defaults (XSRF protection off
# weakens file-upload protection).
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml << 'EOF'
[server]
port = 8888
address = "0.0.0.0"
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF

# Port and address are also passed explicitly so the binding does not depend on the config file.
streamlit run app.py --server.port 8888 --server.address 0.0.0.0
