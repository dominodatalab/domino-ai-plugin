# Identity and limits behind the App proxy

Symptoms that come from how Domino's proxy treats requests rather than from the App's build. How to call Domino as the publisher is in [domino-apps](../domino-apps/SKILL.md) and [domino-api-intro](../domino-api-intro/SKILL.md).

## Identity

Domino authenticates each request before it reaches the App. What the App receives depends on the deployment setting `SecureIdentityPropagationToAppsEnabled`:

| Setting | The App receives |
|---|---|
| On | `domino-username`, plus `Authorization: Bearer <jwt>`: a short-lived token for the viewer whose `preferred_username` claim is the viewer's username |
| Off | `domino-username` only (`Anonymous` for anonymous viewers) |

Acting for viewers is not available on Domino 6.1: the token identifies the viewer, and Domino API routes reject it, often with 500. Call Domino as the publisher (`$DOMINO_API_PROXY`, no `Authorization` header) and scope per-viewer data in the App by the viewer's username. Read the viewer from the token's `preferred_username` claim (`sub` is the Domino user id) when a token arrives, `domino-username` otherwise. To trust the claims, verify the RS256 signature against the Domino realm's JWKS (`<issuer>/protocol/openid-connect/certs`) and pin the issuer `https://<domino-domain>/auth/realms/DominoRealm`.

`DOMINO_API_HOST` runs a request without an `Authorization` header as the publisher.

| Symptom | Cause | Fix |
|---|---|---|
| No `Authorization` header reaches the App | `SecureIdentityPropagationToAppsEnabled` is off | Read `domino-username`, or ask an administrator to turn the setting on |
| A call to the Domino API with the viewer's token fails, often with 500 | Domino 6.1 does not accept the viewer's token on API routes | Make the call as the publisher and filter by the viewer's username |
| Every viewer sees the publisher's data | Calls without `Authorization` run as the publisher | Filter results by the viewer's username where data is per viewer |
| Links or redirects point at `127.0.0.1` or an internal host | Built from `DOMINO_API_HOST` or `DOMINO_USER_HOST` | Use relative URLs; put the deployment's public URL in a project environment variable |
| Publisher calls fail against `localhost:8899` | The token endpoint was hard-coded | Call `$DOMINO_API_PROXY/...` with no `Authorization` header, or get a token from `$DOMINO_API_PROXY/access-token` |

## Sign-in redirects

A request to the App without browser credentials gets a 302 to the sign-in page.

| Symptom | Cause | Fix |
|---|---|---|
| The page's `fetch` throws `Unexpected token '<'` or returns the sign-in page | The session expired while the page was open; `fetch` followed the redirect | When a response is redirected or `text/html`, reload the page so the browser signs in again |
| `curl` or a script gets 302 to the sign-in page | No browser credentials | Open the App in a browser; do not follow redirects in scripts (`curl` without `-L`) |

## Limits and branding

| Symptom | Cause | Fix |
|---|---|---|
| 404 on assets or `api/` only when the URL has no trailing slash | `<prefix>` and `<prefix>/` both reach the App as `/`, with no redirect, so relative URLs resolve one level up | First in the entry page's `<head>`: `<script>if (!location.pathname.endsWith('/')) location.replace(location.pathname + '/' + location.search + location.hash)</script>`; server-rendered Apps can emit `<base href>` set to `DOMINO_RUN_HOST_PATH` instead |
| Works, then breaks after a restart or republish | A hard-coded prefix; it differs: `/apps-internal/<id>`, `/apps/<vanity>`, `/modelproducts/<id>` | Read `DOMINO_RUN_HOST_PATH`, which holds the current prefix with a trailing slash |
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
