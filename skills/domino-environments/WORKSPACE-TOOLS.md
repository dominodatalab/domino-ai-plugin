# Workspace tools and IDE configuration

How an environment declares the IDEs a Workspace can launch, and how to customize them. Creating and editing environments: [SKILL.md](./SKILL.md).

## Pluggable Workspace Tools

The **Pluggable Workspace Tools** field of an environment definition is YAML mapping a tool key to how Domino starts and proxies it. A Workspace session is reachable on one port, the tool's `httpProxy.port`; the Domino Standard Environment tools all use 8888. The DSE ships the four entries below (start scripts under `/opt/domino/workspaces/`):

```yaml
jupyter:
  title: "Jupyter (Python, R, Julia)"
  iconUrl: "/assets/images/workspace-logos/Jupyter.svg"
  start: [ "/opt/domino/workspaces/jupyter/start" ]
  supportedFileExtensions: [ ".ipynb" ]
  httpProxy:
    port: 8888
    rewrite: false
    internalPath: "/{{ownerUsername}}/{{projectName}}/{{sessionPathComponent}}/{{runId}}/{{#if pathToOpen}}tree/{{pathToOpen}}{{/if}}"
    requireSubdomain: false
jupyterlab:
  title: "JupyterLab"
  iconUrl: "/assets/images/workspace-logos/jupyterlab.svg"
  start: [ "/opt/domino/workspaces/jupyterlab/start" ]
  httpProxy:
    internalPath: "/{{ownerUsername}}/{{projectName}}/{{sessionPathComponent}}/{{runId}}/{{#if pathToOpen}}tree/{{pathToOpen}}{{/if}}"
    port: 8888
    rewrite: false
    requireSubdomain: false
vscode:
  title: "vscode"
  iconUrl: "/assets/images/workspace-logos/vscode.svg"
  start: [ "/opt/domino/workspaces/vscode/start" ]
  httpProxy:
    port: 8888
    requireSubdomain: false
rstudio:
  title: "RStudio"
  iconUrl: "/assets/images/workspace-logos/Rstudio.svg"
  start: [ "/opt/domino/workspaces/rstudio/start" ]
  httpProxy:
    port: 8888
    requireSubdomain: false
```

Keys per tool: `title`, `iconUrl`, `start` (command array), optional `supportedFileExtensions`, and `httpProxy` with `port` (required), `internalPath`, `rewrite` (URL rewriting, default false) and `requireSubdomain` (default false; needs a deployment configured for subdomains). The environments API carries the same data under different keys in `workspaceTools[]`: the map key becomes `name`, `start` becomes `startScripts`, `httpProxy` becomes `proxyConfig` ([API.md](./API.md)); do not POST the YAML keys. Cluster-node environments leave this field empty.

Source: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/work-with-pluggable-workspaces/add-workspace-ides

## Replace or add a tool (native workspaces)

To run a tool from your own image, add a start script (in the base image or via Dockerfile instructions) and point the tool's `start` at it. Domino's JupyterLab script writes `$HOME/.jupyter/jupyter_lab_config.py` with the proxy base URL (`/$DOMINO_PROJECT_OWNER/$DOMINO_PROJECT_NAME/notebookSession/$DOMINO_RUN_ID`), the working directory (`DOMINO_WORKING_DIR`) and the required `Content-Security-Policy: frame-ancestors *` header, then starts the server on 8888. Copy the documented script rather than hand-rolling the config, and keep it as the environment's start script, not a Dockerfile edit of `/home/domino` (that user does not exist; containers run as `ubuntu`):

https://docs.domino.ai/cloud/platform-capabilities/core-concepts/compute-environments/work-with-pluggable-workspaces/configure-native-workspaces

Jupyter's own token check is handled inside Domino's start script because the Workspace is reachable only through Domino's authenticated proxy; do not add extra `jupyter_notebook_config.py` lines to disable auth in your Dockerfile.

## VS Code

- Extensions on every launch (environment **Pre Run Script**; scripts run as root, so name the `ubuntu` home explicitly and hand ownership back):
  ```shell
  code-server --install-extension <publisher.extension> --extensions-dir /home/ubuntu/.local/share/code-server/extensions
  chown -R ubuntu:ubuntu /home/ubuntu/.local/share/code-server
  ```
- Extensions baked into the image:
  ```dockerfile
  USER root
  RUN code-server --install-extension <publisher.extension> --extensions-dir /home/ubuntu/.local/share/code-server/extensions \
      && chown -R ubuntu:ubuntu /home/ubuntu/.local/share/code-server
  USER ubuntu
  ```
  For a `.vsix`: `code-server --install-extension /tmp/ext.vsix --force`.
- Adding VS Code to an image without it: install `code-server`, write a start script that runs `code-server $DOMINO_WORKING_DIR --user-data-dir $DOMINO_WORKING_DIR/.vscode --auth none --bind-addr 0.0.0.0:8888 --extensions-dir /home/ubuntu/.local/share/code-server/extensions` (start scripts run as `ubuntu`), and add a `vscode` entry to the tools YAML. `--auth none` is correct here because Domino's proxy authenticates the session. Full script: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace/launch-a-vs-code-workspace

## RStudio preferences

RStudio 1.3+ reads `/home/ubuntu/.config/rstudio/rstudio-prefs.json`. Write it from the **Pre Run Script**:

```shell
mkdir -p /home/ubuntu/.config/rstudio
cat <<'EOF' > /home/ubuntu/.config/rstudio/rstudio-prefs.json
{ "editor_theme": "Cobalt", "posix_terminal_shell": "bash" }
EOF
chown -R ubuntu:ubuntu /home/ubuntu/.config/rstudio
```

Or copy a `rstudio-prefs.json` saved in the Project. Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/launch-a-workspace/open-rstudio-with-custom-preferences

## Several apps in one Workspace

Only the tool port is proxied. The DSE includes jupyter-server-proxy; configure `c.ServerProxy.servers` in `/home/ubuntu/.jupyterlab/jupyter_lab_config.py` from the Dockerfile to expose Dash, TensorBoard or code-server at `.../notebookSession/<run id>/proxy/<port>/`. Reserved ports: 80 (nginx) and 9000 (executor). Docs: https://docs.domino.ai/cloud/platform-capabilities/core-concepts/workspaces/run-multiple-apps-in-a-workspace

## SSH-enabled environment

For Workspace SSH access the image needs `openssh-server`:

```dockerfile
USER root
RUN apt-get update && apt-get install -y openssh-server && mkdir -p /var/run/sshd && chmod 0755 /var/run/sshd
USER ubuntu
```

Domino starts `sshd` when the Workspace launches with SSH enabled; see [domino-workspaces](../domino-workspaces/SKILL.md).

## Home-directory layout

- User `ubuntu`, home `/home/ubuntu`; `DOMINO_USER`, `DOMINO_USER_ID`, `DOMINO_GROUP` and `DOMINO_GROUP_ID` hold the names and ids.
- Home Directory Persistence (Workspaces) keeps `/home/ubuntu` across sessions and requires `rsync` in the image.
- Package Persistence requires `uv` (Python) and `renv` (R) in custom images.
