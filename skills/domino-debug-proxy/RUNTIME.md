# Identity, consent and limits behind the App proxy

Symptoms that come from how Domino's proxy treats requests rather than from the App's build. How to call Domino as the viewer or the publisher is in [domino-apps](../domino-apps/SKILL.md) and [domino-api-intro](../domino-api-intro/SKILL.md).

## Identity

Domino authenticates each request before it reaches the App. What the App receives depends on the App's identity mode:

| Mode | The App receives | Domino API routes that accept the viewer's token |
|---|---|---|
| Secure identity propagation (default) | `Authorization: Bearer <jwt>`: a token for Apps (audience `apps`, valid for about 5 minutes), plus `domino-username` copied from it | Dataset snapshot file reads and Data Source lookup by name; other routes reject it, often with 500 |
| Extended identity propagation (the App version is published with it on by a SysAdmin or CloudAdmin, cannot be turned off, and each viewer consents: 8 hours by default, up to 30 days) | `Authorization: Bearer` with the viewer's own credential (the browser session token, or the Personal Access Token a script sent); no `domino-username`, and a client can send its own | Every route the viewer may call |
| Secure identity propagation off (deployment setting) | `domino-username` only | None |

Read the viewer from the token's `preferred_username` claim (`sub` is the Domino user id), and `domino-username` only when no token arrived. To trust the claims, verify the RS256 signature against the Domino realm's JWKS (`<issuer>/protocol/openid-connect/certs`) and pin the issuer `https://<domino-domain>/auth/realms/DominoRealm`; do not require audience `apps`, which extended-mode tokens do not carry. App Preview runs in the default mode unless an administrator turns on extended identity propagation in the preview's **Settings** panel.

`DOMINO_API_HOST` inside an App can be an API gateway in the App's pod (`http://127.0.0.1:<port>`). It accepts browser-session, service-account and Personal Access Token credentials, rejects Domino CLI login tokens with 403, and runs a request without an `Authorization` header as the publisher.

| Symptom | Cause | Fix |
|---|---|---|
| Viewer name is missing, `Anonymous`, or set by the client | The App reads `domino-username`, which extended-mode Apps do not receive and a client can forge | Read `preferred_username` from the bearer token |
| Token verification fails for every viewer of an extended-mode App | The verifier requires audience `apps` | Check signature and issuer only |
| A viewer call to the Domino API fails, often with 500 | Default mode: the token is accepted only by the data-access routes above | Publish an App version with extended identity propagation and have the viewer consent, or make the call as the publisher |
| A viewer call works in the request and fails later in a background task | The default-mode token expired, or the viewer's consent did | Use the token of the request being served; never store it for later |
| 403 when the App forwards a script's token | The script sent a Domino CLI login token | Send a Personal Access Token |
| Calls meant for the viewer return the publisher's data | No `Authorization` header reached `DOMINO_API_HOST`: the token was dropped, sent empty, or the call was retried without it | Forward the viewer's token on every viewer call; answer 401 when it is missing |
| Viewer calls rejected although the token is present | The forwarded value is `Bearer Bearer ...` | Forward the header unchanged, or strip `Bearer ` before adding it again |
| Links or redirects point at `127.0.0.1` or an internal host | Built from `DOMINO_API_HOST` or `DOMINO_USER_HOST` | Use relative URLs; put the deployment's public URL in a project environment variable |
| Publisher calls fail against `localhost:8899` | The token endpoint was hard-coded | Call `$DOMINO_API_PROXY/...` with no `Authorization` header, or get a token from `$DOMINO_API_PROXY/access-token` |

## Consent and scripts

For an App with extended identity propagation, Domino sends every request from a viewer who has not consented, JSON included, to `/app-consent?appId=<id>&callback=<url>` with a 302; a request with no credentials goes to the sign-in page.

| Symptom | Cause | Fix |
|---|---|---|
| The page's `fetch` throws `Unexpected token '<'` or returns the consent page | Consent expired while the page was open; `fetch` followed the redirect | When a response is redirected or `text/html`, reload the page so the browser shows the prompt |
| `curl` or a script gets 302 to `/app-consent` | No consent for the script's user | Open the App once in a browser as that user and consent |
| `curl` or a script gets 302 to the sign-in page | No credentials | Send `Authorization: Bearer <Personal Access Token>` |

## Limits and branding

| Symptom | Cause | Fix |
|---|---|---|
| 404 on assets or `api/` only when the URL has no trailing slash | `<prefix>` and `<prefix>/` both reach the App as `/`, with no redirect, so relative URLs resolve one level up | First in the entry page's `<head>`: `<script>if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)</script>`; server-rendered Apps can emit `<base href>` set to `DOMINO_RUN_HOST_PATH` instead |
| Works in App Preview, breaks when published, or the reverse | A hard-coded prefix; it differs: `/preview/<id>`, `/apps-internal/<id>`, `/apps/<vanity>`, `/modelproducts/<id>` | Read `DOMINO_RUN_HOST_PATH`, which holds the current prefix with a trailing slash |
| Generated URLs lack the prefix | Code expects `X-Script-Name`, which Domino never sends | Use `DOMINO_RUN_HOST_PATH` |
| `GET /favicon.ico` 404 in the browser console | Domino inserts a `/favicon.ico` link at the first literal `<head>` of HTML responses (not compressed ones), and that path 404s on the Apps host | Add a relative `<link rel="icon" href="static/favicon.svg">` later in `<head>` |
| The tab shows the deployment's title, not the App's | Domino inserts its `<title>` before the App's, and the first one wins | Set `document.title` from script |
| Another App's cookies or `localStorage` values appear | Every App on the deployment shares one origin | Give cookies App-specific names and `Path` set to `DOMINO_RUN_HOST_PATH` without the trailing slash; prefix `localStorage` keys and keep viewer data out of it. Domino's own session cookies are removed before requests reach the App |
| The App URL opened directly answers 400, inside Domino it works | The deployment allows Apps only inside Domino's page | Open the App from Domino |
| Server-sent events arrive all at once | The proxy buffers the response | Send `X-Accel-Buffering: no` and `Cache-Control: no-cache` with the stream |
| WebSocket or SSE connection drops after 300 s idle | Idle connections close after 300 s | Send a heartbeat (an SSE comment line, a WebSocket ping) well inside 300 s, and reconnect on close |
| A long request fails at 300 s | 300 s read timeout | Answer quickly and run the work in a Job or background task, then poll |
| Upload fails with 413 | Request body over 25 MiB (the default limit) | Upload in parts under the limit |
| WebSocket does not connect | An absolute or root-relative `ws` URL | `const u = new URL('ws', document.baseURI); u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'` |
