//! Who the viewer is, and calls to the Domino API as the viewer or as the App's publisher.
//!
//! - **Identity.** Domino authenticates every request before it reaches the App and forwards the
//!   viewer's token as `Authorization: Bearer <jwt>`; its `preferred_username` claim names the viewer.
//!   The `domino-username` header is a convenience copy that Apps with extended identity propagation
//!   do not receive, and there a client can send its own, so the token comes first.
//! - **Viewer calls.** Without extended identity propagation the token only identifies the viewer and
//!   most Domino routes reject it. With it (the App is published with it on, and the viewer consented)
//!   the token is the viewer's own credential with their full permissions.
//! - **Publisher calls.** `DOMINO_API_PROXY` adds the publisher's token to any request sent without
//!   an `Authorization` header.
//!
//! The App chooses per call. Tokens are never logged.

use axum::http::{HeaderMap, StatusCode, header::AUTHORIZATION};
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Where the viewer's name came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NameSource {
    /// The `preferred_username` claim of the forwarded token.
    Token,
    /// The `domino-username` header, used only when the request carries no token.
    Header,
}

/// The viewer's Domino username from the forwarded token's `preferred_username` claim, or from the
/// `domino-username` header when the request carries no token. Domino checked the token before
/// forwarding the request; this function does not verify its signature itself. For decisions that
/// grant access, verify the token, or, on an App with extended identity propagation, call the Domino
/// API as the viewer; without it Domino rejects the viewer's token on most routes.
#[must_use]
pub fn viewer_name(headers: &HeaderMap) -> Option<(String, NameSource)> {
    if let Some(token) = bearer(headers) {
        let payload = token.split('.').nth(1)?;
        let bytes = URL_SAFE_NO_PAD.decode(payload.trim_end_matches('=')).ok()?;
        let claims: Value = serde_json::from_slice(&bytes).ok()?;
        let name = claims.get("preferred_username")?.as_str()?;
        return Some((name.to_owned(), NameSource::Token));
    }
    let name = headers.get("domino-username")?.to_str().ok()?;
    Some((name.to_owned(), NameSource::Header))
}

/// Whose permissions a Domino API call uses.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Identity {
    /// The person viewing the App (needs extended identity propagation for most routes).
    #[default]
    Viewer,
    /// The person who published the App.
    Publisher,
}

/// An error to return to the browser: a status and a message that says what to fix.
pub type ApiError = (StatusCode, String);

const NO_VIEWER_TOKEN: &str = "No viewer token: open the App through Domino. If it was, secure \
     identity propagation is off on this deployment.";

const VIEWER_REJECTED: &str = " Without extended identity propagation, most Domino API routes reject \
     the viewer's token.";

/// Domino API client configured from `DOMINO_API_HOST` and `DOMINO_API_PROXY`.
#[derive(Clone)]
pub struct DominoApi {
    http: reqwest::Client,
    host: Option<String>,
    proxy: Option<String>,
}

impl DominoApi {
    /// Builds a client from explicit base URLs (tests point them at a mock server).
    #[must_use]
    pub fn new(http: reqwest::Client, host: Option<String>, proxy: Option<String>) -> Self {
        Self { http, host, proxy }
    }

    /// Reads the base URLs Domino injects into every App.
    #[must_use]
    pub fn from_env(http: reqwest::Client) -> Self {
        Self::new(
            http,
            std::env::var("DOMINO_API_HOST").ok(),
            std::env::var("DOMINO_API_PROXY").ok(),
        )
    }

    /// `GET` a Domino API path (for example `/api/users/v1/self`) as `identity` and return its JSON.
    ///
    /// # Errors
    ///
    /// 401 when the viewer token is missing or empty, 503 when the base URL is not set, Domino's own status
    /// when it rejects the call, and 502 when it cannot be reached or returns invalid JSON.
    pub async fn get(
        &self,
        identity: Identity,
        headers: &HeaderMap,
        path: &str,
    ) -> Result<Value, ApiError> {
        let request = match identity {
            Identity::Viewer => {
                let token = bearer(headers)
                    .ok_or_else(|| (StatusCode::UNAUTHORIZED, NO_VIEWER_TOKEN.to_owned()))?;
                let host = self
                    .host
                    .as_deref()
                    .ok_or_else(|| unset("DOMINO_API_HOST"))?;
                self.http.get(format!("{host}{path}")).bearer_auth(token)
            }
            Identity::Publisher => {
                let proxy = self
                    .proxy
                    .as_deref()
                    .ok_or_else(|| unset("DOMINO_API_PROXY"))?;
                self.http.get(format!("{proxy}{path}"))
            }
        };
        let response = request.send().await.map_err(|err| {
            tracing::error!(%err, ?identity, path, "Domino API unreachable");
            (StatusCode::BAD_GATEWAY, "Domino API unreachable".to_owned())
        })?;
        let status = response.status();
        if !status.is_success() {
            tracing::warn!(%status, ?identity, path, "Domino API rejected the call");
            let hint = if identity == Identity::Viewer && matches!(status.as_u16(), 401 | 403 | 500)
            {
                VIEWER_REJECTED
            } else {
                ""
            };
            return Err((
                status,
                format!("Domino API answered {status} for the {identity:?} identity.{hint}"),
            ));
        }
        response.json::<Value>().await.map_err(|err| {
            tracing::error!(%err, path, "Domino API returned invalid JSON");
            (
                StatusCode::BAD_GATEWAY,
                "Domino API returned invalid JSON".to_owned(),
            )
        })
    }
}

/// The viewer's token from `Authorization: Bearer <token>`; `None` when it is missing or empty.
fn bearer(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
        .map(str::trim)
        .filter(|token| !token.is_empty())
}

fn unset(name: &str) -> ApiError {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        format!("{name} is not set; run inside Domino"),
    )
}
