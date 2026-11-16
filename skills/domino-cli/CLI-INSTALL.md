# Install the Domino CLI, sign in, proxies, recovery

Sources: https://docs.domino.ai/cloud/reference/cli/install-the-cli,
https://docs.domino.ai/cloud/reference/cli/use-the-cli-behind-a-proxy,
https://docs.domino.ai/cloud/reference/cli/force-restore-a-local-project,
https://docs.domino.ai/cloud/reference/cli/move-project-between-deployments.

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

The CLI prompts you to authorize it with Domino:

1. Open `https://<your-domino-url>/authorizeCli` in a browser. It can be on any device, so this
   also works from an SSH session, a Workspace or a headless server. Sign in if asked.
2. Copy the authorization code the page shows.
3. Paste it at the CLI prompt and press Enter. The CLI prints that the login succeeded.

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
