# Install the Domino CLI, sign in, proxies, recovery

Sources: https://docs.domino.ai/cloud/reference/cli/install-the-cli,
https://docs.domino.ai/cloud/reference/cli/use-the-cli-behind-a-proxy,
https://docs.domino.ai/cloud/reference/cli/force-restore-a-local-project,
https://docs.domino.ai/cloud/reference/cli/move-project-between-deployments (6.3 pages identical).

## Graphical install (laptop)

1. In the Domino UI, **Account > Download CLI**, choose the operating system.
2. Run the installer.
   - **Linux**: `sh domino-install-unix.sh` from the download folder.
   - **Windows**: use the 64-bit build bundled with a JRE; the 32-bit build is deprecated.
   - **macOS**: the installer asks for administrator credentials. Without them, click **Cancel**,
     then **Ignore** when it offers to update `PATH`, and add
     `export PATH="$PATH:/Applications/domino"` to your shell profile yourself.
3. Close the terminal completely and open a new one before the first `domino` command.

Supported: recent Ubuntu Linux, Windows 10, macOS.

## Headless install (server, Domino Workspace)

```bash
apt install openjdk-8-jre-headless
wget https://<domino-url>/download/client/unix -O /tmp/domino-install-unix.sh
sh /tmp/domino-install-unix.sh
```

`<domino-url>` is the deployment the client will talk to; the installer is served by Domino
itself. If the installer stops with an `AtkWrapper` error, comment out the
`assistive_technologies` line in `/etc/java-8-openjdk/accessibility.properties`:

```bash
sed -i 's/^assistive_technologies=/#assistive_technologies=/g' /etc/java-8-openjdk/accessibility.properties
```

## Sign in

```bash
domino login https://<your-domino-url>
```

The CLI opens the default browser on the sign-in page and receives the authorization when you
finish; the browser tab then says authentication succeeded. If no browser opens, the terminal
prints the URL: open it on the **same machine**, because the sign-in redirects to a local address.

Machine without a usable browser (SSH session, Workspace, headless server):

```bash
domino login --device https://<your-domino-url>
# To sign in, use a web browser to open the page https://<your-domino-url>/auth/realms/DominoRealm/device
# and enter the code ABCD-EFGH.
```

Open the verification URL on any device, enter the code, sign in, review the requested access
and choose **Grant Access**; the CLI, which polls in the background, prints `Login succeeded`.
Codes expire after a short time; rerun the command to get a new one. This is the OAuth 2.0
Device Authorization Grant (RFC 8628).

CLI versions older than **6.2.3** use a different authentication client and fail to log in after
a Domino upgrade: download and reinstall the current CLI from **Download CLI**.

## Behind an HTTP proxy

Settings live in `domino.vmoptions`. Do not edit only the copy in the installation directory
(`/Applications/domino` on macOS, `C:\Users\<you>\AppData\Local\Programs\domino` on Windows);
a reinstall overwrites it. Instead:

1. Append `-include-options ~/.domino/domino.vmoptions` as the **last** line of the installed
   `domino.vmoptions` (Windows: the full path to the user file).
2. `mkdir -p ~/.domino` and create `~/.domino/domino.vmoptions`:

```text
-Dhttp.proxyHost=YOURPROXYHOST
-Dhttp.proxyPort=1234
-Dhttps.proxyHost=YOURPROXYHOST
-Dhttps.proxyPort=1234
```

No `http://` or `https://` in the host values. Available keys also include
`-Ddomino.defaultHost=`, `-Dhttp.nonProxyHosts=` and `-Dhttps.nonProxyHosts=`.

Proxy authentication, appended to the same user file:

```text
# Basic
-Djava.net.useSystemProxies=false
-Djdk.http.auth.tunneling.disabledSchemes=
-Dhttps.proxyUser=YOURPROXYUSER
-Dhttps.proxyPassword=YOURPROXYPASSWORD
-Dhttp.proxyUser=YOURPROXYUSER
-Dhttp.proxyPassword=YOURPROXYPASSWORD
# NTLM (in addition to the Basic lines)
-Dhttp.auth.ntlm.domain=YOURNTLMDOMAIN
-Dhttps.auth.ntlm.domain=YOURNTLMDOMAIN
```

No quotes around values, even when the password contains spaces; the NTLM username is
case-sensitive; leave a blank line at the end of the file. The file then holds the proxy
password in plaintext on your laptop: restrict it to your user (`chmod 600`) and keep it out of
version control.

## Force-restore a local project

When the local metadata is corrupt (a file changed during a sync while file locking was off,
for example) and CLI commands error:

```bash
cd <project folder>
rm -rf .domino
domino restore          # enter the project name when prompted
```

Server files missing locally are downloaded; delete what you do not need. Local files that differ
from the server are pushed on the next `domino sync`.

## Move a project between deployments

Only the **latest files** move: no history, no revisions, no access or collaboration settings.

```bash
cd <your-project>        # must be an up-to-date local copy (domino get / domino sync on the source first)
rm -rf .domino           # Windows: rmdir /s/q .domino and del .domino*
domino login https://<target deployment>
domino init
domino upload
```

Then open the project on the target deployment and set visibility and collaborators again.
