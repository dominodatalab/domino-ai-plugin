//! Calls to the Domino API as the viewer or as the App's publisher.
//!
//! - **Viewer.** Domino's proxy forwards the viewer's token as `Authorization: Bearer <jwt>`. By
//!   default its scope only identifies the viewer. With extended identity propagation (turned on
//!   for the App when an administrator publishes it, and after the viewer consents) the same token
//!   carries the viewer's full Domino permissions.
//! - **Publisher.** `DOMINO_API_PROXY` adds the publisher's token to any request sent without an
//!   `Authorization` header.
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
    /// The `domino-username` header set by Domino's proxy.
    Header,
    /// The `preferred_username` claim of the forwarded token, read without verifying its signature.
    TokenClaim,
}

/// The viewer's Domino username: the `domino-username` header, or, where that header is absent (Apps
/// with extended identity propagation), the `preferred_username` claim of the forwarded token. The
/// claim is not verified here, so use it for display; for decisions, call the Domino API as the
/// viewer, which checks the token.
#[must_use]
pub fn viewer_name(headers: &HeaderMap) -> Option<(String, NameSource)> {
    if let Some(name) = headers
        .get("domino-username")
        .and_then(|value| value.to_str().ok())
    {
        return Some((name.to_owned(), NameSource::Header));
    }
    let payload = bearer(headers)?.split('.').nth(1)?;
    let bytes = URL_SAFE_NO_PAD.decode(payload.trim_end_matches('=')).ok()?;
    let claims: Value = serde_json::from_slice(&bytes).ok()?;
    let name = claims.get("preferred_username")?.as_str()?;
    Some((name.to_owned(), NameSource::TokenClaim))
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

const NO_VIEWER_TOKEN: &str = "No viewer token. The App must be published with extended identity \
     propagation, and the viewer must accept the consent prompt.";

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
    /// 401 when the viewer token is missing, 503 when the base URL is not set, Domino's own status
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
            return Err((
                status,
                format!("Domino API answered {status} for the {identity:?} identity"),
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

/// The viewer's token from `Authorization: Bearer <token>`.
fn bearer(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
}

fn unset(name: &str) -> ApiError {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        format!("{name} is not set; run inside Domino"),
    )
}
