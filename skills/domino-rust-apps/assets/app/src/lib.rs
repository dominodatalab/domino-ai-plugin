//! A Domino App on axum and askama.
//!
//! Domino's proxy serves the App under a per-App prefix (`DOMINO_RUN_HOST_PATH`) and forwards
//! requests rooted at `/`. Every URL the browser sees is therefore relative: `static/app.css`,
//! `api/whoami`, `Redirect::to("./")`. A root-absolute `/static/...` or `Redirect::to("/")`
//! leaves the App.

pub mod domino;
pub mod http;

use std::{env, sync::Arc, time::Duration};

use askama::Template;
use axum::{
    Json, Router,
    extract::{Query, State},
    http::{HeaderMap, StatusCode},
    response::{Html, IntoResponse, Redirect, Response},
    routing::{get, post},
};
use domino::{ApiError, DominoApi, Identity, NameSource, viewer_name};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::{PgPool, postgres::PgPoolOptions};
use tower_http::{
    services::ServeDir,
    trace::{DefaultMakeSpan, DefaultOnResponse, TraceLayer},
};
use tracing::Level;

/// Model endpoint settings from Project environment variables, read once at startup.
struct ModelEndpoint {
    url: String,
    token: String,
}

/// Shared, read-only state. Startup reads configuration and writes nothing.
#[derive(Clone)]
pub struct AppState {
    http: reqwest::Client,
    model: Option<Arc<ModelEndpoint>>,
    domino: DominoApi,
    db: Option<PgPool>,
    /// The build label `app.sh` started (`APP_BUILD`, for example `2026.10.15`).
    build: Option<Arc<str>>,
}

impl AppState {
    /// Reads configuration from environment variables and builds the clients. Connects to nothing:
    /// the database pool opens connections on first use, so the App starts even when Postgres is down.
    ///
    /// - `MODEL_API_URL`, `MODEL_API_TOKEN`: the model endpoint (the route answers 503 without them).
    /// - `DATABASE_URL`: Postgres, for example `postgres://user:pass@host/db?sslmode=verify-full`
    ///   (the database route answers 503 without it).
    /// - `DOMINO_API_HOST`, `DOMINO_API_PROXY`: injected by Domino.
    /// - `APP_BUILD`: the build label, set by `app.sh` and reported by `/healthz`.
    ///
    /// # Errors
    ///
    /// Returns an error if a client cannot be built or `DATABASE_URL` cannot be parsed.
    pub fn from_env() -> Result<Self, http::BoxError> {
        let model = match (env::var("MODEL_API_URL"), env::var("MODEL_API_TOKEN")) {
            (Ok(url), Ok(token)) => Some(Arc::new(ModelEndpoint { url, token })),
            _ => None,
        };
        let db = match env::var("DATABASE_URL") {
            Ok(url) => Some(
                PgPoolOptions::new()
                    .max_connections(5)
                    .acquire_timeout(Duration::from_secs(5))
                    .connect_lazy(&url)?,
            ),
            Err(_) => None,
        };
        Ok(Self {
            http: http::external_client()?,
            model,
            domino: DominoApi::from_env(http::internal_client()?),
            db,
            build: env::var("APP_BUILD").ok().map(Arc::from),
        })
    }
}

/// `?as=publisher` switches a Domino API route from the viewer's identity to the publisher's.
#[derive(Deserialize)]
struct CallAs {
    #[serde(default, rename = "as")]
    identity: Identity,
}

#[derive(Template)]
#[template(path = "index.html")]
struct IndexPage<'a> {
    title: &'a str,
    username: &'a str,
}

#[derive(Serialize)]
struct WhoAmI {
    username: Option<String>,
    source: Option<NameSource>,
}

/// The App's routes. Paths start with `/` here; the browser reaches them through relative URLs.
///
/// ```
/// let router = domino_rust_app::app(domino_rust_app::AppState::from_env().unwrap());
/// # drop(router);
/// ```
pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/", get(index))
        .route("/healthz", get(healthz))
        .route("/api/whoami", get(whoami))
        .route("/api/me", get(me))
        .route("/api/projects", get(projects))
        .route("/api/db", get(db_check))
        .route("/api/predict", post(predict))
        .route("/refresh", post(refresh))
        // ServeDir's directory redirect sends a root-absolute Location; turn it off.
        .nest_service(
            "/static",
            ServeDir::new("static").redirect_to_trailing_slash(false),
        )
        // One INFO line per request: method, path, status, latency. Headers are not logged.
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().level(Level::INFO))
                .on_response(DefaultOnResponse::new().level(Level::INFO)),
        )
        .with_state(state)
}

async fn index(headers: HeaderMap) -> Response {
    let name = viewer_name(&headers).map(|(name, _)| name);
    let page = IndexPage {
        title: "Domino Rust App",
        username: name.as_deref().unwrap_or("Anonymous"),
    };
    match page.render() {
        Ok(html) => Html(html).into_response(),
        Err(err) => {
            tracing::error!(%err, "template render failed");
            StatusCode::INTERNAL_SERVER_ERROR.into_response()
        }
    }
}

/// Liveness plus the running build's label, so a deploy or rollback can be confirmed from outside.
async fn healthz(State(state): State<AppState>) -> Json<Value> {
    Json(json!({ "status": "ok", "build": state.build.as_deref() }))
}

/// The viewer's name and where it came from (`header` or `token_claim`).
async fn whoami(headers: HeaderMap) -> Json<WhoAmI> {
    let viewer = viewer_name(&headers);
    Json(WhoAmI {
        source: viewer.as_ref().map(|(_, source)| *source),
        username: viewer.map(|(name, _)| name),
    })
}

/// The Domino user record, as the viewer (default) or the publisher (`?as=publisher`).
async fn me(
    State(state): State<AppState>,
    Query(call): Query<CallAs>,
    headers: HeaderMap,
) -> Result<Json<Value>, ApiError> {
    state
        .domino
        .get(call.identity, &headers, "/api/users/v1/self")
        .await
        .map(Json)
}

/// Projects visible to the viewer (default) or the publisher; the two lists differ.
async fn projects(
    State(state): State<AppState>,
    Query(call): Query<CallAs>,
    headers: HeaderMap,
) -> Result<Json<Value>, ApiError> {
    state
        .domino
        .get(
            call.identity,
            &headers,
            "/api/projects/beta/projects?limit=25",
        )
        .await
        .map(Json)
}

/// Checks the Postgres connection with `SELECT 1`. Queries take their values as bind parameters
/// (`sqlx::query("... WHERE id = $1").bind(id)`), never string formatting.
async fn db_check(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let Some(pool) = state.db.as_ref() else {
        return Err((
            StatusCode::SERVICE_UNAVAILABLE,
            "DATABASE_URL is not set".to_owned(),
        ));
    };
    let one: i32 = sqlx::query_scalar("SELECT 1")
        .fetch_one(pool)
        .await
        .map_err(|err| {
            tracing::error!(%err, "database query failed");
            (StatusCode::BAD_GATEWAY, "database query failed".to_owned())
        })?;
    Ok(Json(json!({ "database": "ok", "select_1": one })))
}

/// Post/Redirect/Get with a relative `Location`.
async fn refresh() -> Redirect {
    Redirect::to("./")
}

/// Calls a synchronous Domino model endpoint: HTTP Basic auth with the token as both
/// username and password, body `{"data": ...}`. Runs on the server so the token never
/// reaches the browser.
async fn predict(
    State(state): State<AppState>,
    Json(data): Json<Value>,
) -> Result<Json<Value>, (StatusCode, &'static str)> {
    let Some(model) = state.model.as_deref() else {
        return Err((
            StatusCode::SERVICE_UNAVAILABLE,
            "MODEL_API_URL and MODEL_API_TOKEN are not set",
        ));
    };
    let response = state
        .http
        .post(&model.url)
        .basic_auth(&model.token, Some(&model.token))
        .json(&json!({ "data": data }))
        .send()
        .await
        .and_then(reqwest::Response::error_for_status)
        .map_err(|err| {
            tracing::error!(%err, "model endpoint call failed");
            (StatusCode::BAD_GATEWAY, "model endpoint call failed")
        })?;
    let body = response.json::<Value>().await.map_err(|err| {
        tracing::error!(%err, "model endpoint returned invalid JSON");
        (
            StatusCode::BAD_GATEWAY,
            "model endpoint returned invalid JSON",
        )
    })?;
    Ok(Json(body))
}

/// Resolves on Ctrl-C or SIGTERM; Domino stops an App by terminating its container.
///
/// # Panics
///
/// Panics if the signal handlers cannot be installed.
pub async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl-C handler");
    };
    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
    tracing::info!("shutdown signal received, finishing in-flight requests");
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, header},
    };
    use http_body_util::BodyExt;
    use tower::ServiceExt; // for `oneshot`

    fn state(host: Option<String>, proxy: Option<String>, db: Option<PgPool>) -> AppState {
        AppState {
            domino: DominoApi::new(http::internal_client().unwrap(), host, proxy),
            http: http::external_client().unwrap(),
            model: None,
            db,
            build: None,
        }
    }

    fn app_with_domino(host: Option<String>, proxy: Option<String>) -> Router {
        app(state(host, proxy, None))
    }

    #[tokio::test]
    async fn db_route_without_database_url_is_503() {
        let response = send(Request::get("/api/db").body(Body::empty()).unwrap()).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn db_route_reports_an_unreachable_database_as_502() {
        http::install_crypto_provider();
        let pool = PgPoolOptions::new()
            .acquire_timeout(Duration::from_secs(1))
            .connect_lazy("postgres://user:pass@127.0.0.1:1/db")
            .unwrap();
        let app = app(state(None, None, Some(pool)));
        let response = app
            .oneshot(Request::get("/api/db").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    }

    fn test_app() -> Router {
        app_with_domino(None, None)
    }

    /// A stand-in for the Domino API that echoes the path and `Authorization` header it received.
    async fn mock_domino() -> String {
        let echo = Router::new().fallback(|headers: HeaderMap, uri: axum::http::Uri| async move {
            let authorization = headers
                .get(header::AUTHORIZATION)
                .and_then(|value| value.to_str().ok())
                .map(str::to_owned);
            Json(json!({ "path": uri.to_string(), "authorization": authorization }))
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        tokio::spawn(async move { axum::serve(listener, echo).await.unwrap() });
        url
    }

    #[tokio::test]
    async fn viewer_call_without_token_is_401() {
        let app = app_with_domino(Some(mock_domino().await), None);
        let response = app
            .oneshot(Request::get("/api/me").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert!(
            body_text(response)
                .await
                .contains("open the App through Domino")
        );
    }

    #[tokio::test]
    async fn viewer_call_with_an_empty_token_is_401() {
        let app = app_with_domino(Some(mock_domino().await), None);
        let request = Request::get("/api/me")
            .header(header::AUTHORIZATION, "Bearer ")
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn rejected_viewer_call_names_extended_identity_propagation() {
        let failing = Router::new().fallback(|| async { StatusCode::INTERNAL_SERVER_ERROR });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        tokio::spawn(async move { axum::serve(listener, failing).await.unwrap() });
        let request = Request::get("/api/me")
            .header(header::AUTHORIZATION, "Bearer viewer-jwt")
            .body(Body::empty())
            .unwrap();
        let response = app_with_domino(Some(url), None)
            .oneshot(request)
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert!(
            body_text(response)
                .await
                .contains("extended identity propagation")
        );
    }

    #[tokio::test]
    async fn viewer_call_forwards_the_viewer_token() {
        let app = app_with_domino(Some(mock_domino().await), None);
        let request = Request::get("/api/me")
            .header(header::AUTHORIZATION, "Bearer viewer-jwt")
            .body(Body::empty())
            .unwrap();
        let body: Value =
            serde_json::from_str(&body_text(app.oneshot(request).await.unwrap()).await).unwrap();
        assert_eq!(body["path"], "/api/users/v1/self");
        assert_eq!(body["authorization"], "Bearer viewer-jwt");
    }

    #[tokio::test]
    async fn publisher_call_goes_through_the_proxy_without_the_viewer_token() {
        let app = app_with_domino(None, Some(mock_domino().await));
        let request = Request::get("/api/projects?as=publisher")
            .header(header::AUTHORIZATION, "Bearer viewer-jwt")
            .body(Body::empty())
            .unwrap();
        let body: Value =
            serde_json::from_str(&body_text(app.oneshot(request).await.unwrap()).await).unwrap();
        assert_eq!(body["path"], "/api/projects/beta/projects?limit=25");
        assert_eq!(body["authorization"], Value::Null);
    }

    async fn send(request: Request<Body>) -> Response {
        test_app().oneshot(request).await.unwrap()
    }

    async fn body_text(response: Response) -> String {
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        String::from_utf8(bytes.to_vec()).unwrap()
    }

    #[tokio::test]
    async fn healthz_returns_ok_json() {
        let response = send(Request::get("/healthz").body(Body::empty()).unwrap()).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body: Value = serde_json::from_str(&body_text(response).await).unwrap();
        assert_eq!(body, json!({ "status": "ok", "build": null }));
    }

    #[tokio::test]
    async fn healthz_reports_the_build_label() {
        let mut labelled = state(None, None, None);
        labelled.build = Some(Arc::from("2026.10.15.2"));
        let response = app(labelled)
            .oneshot(Request::get("/healthz").body(Body::empty()).unwrap())
            .await
            .unwrap();
        let body: Value = serde_json::from_str(&body_text(response).await).unwrap();
        assert_eq!(body["build"], "2026.10.15.2");
    }

    #[tokio::test]
    async fn whoami_reads_domino_username_header() {
        let request = Request::get("/api/whoami")
            .header("domino-username", "jane.doe")
            .body(Body::empty())
            .unwrap();
        let body: Value = serde_json::from_str(&body_text(send(request).await).await).unwrap();
        assert_eq!(body, json!({ "username": "jane.doe", "source": "header" }));

        let request = Request::get("/api/whoami").body(Body::empty()).unwrap();
        let body: Value = serde_json::from_str(&body_text(send(request).await).await).unwrap();
        assert_eq!(body, json!({ "username": null, "source": null }));
    }

    fn token_for(username: &str) -> String {
        use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
        let claims = URL_SAFE_NO_PAD.encode(format!(r#"{{"preferred_username":"{username}"}}"#));
        format!("Bearer e30.{claims}.sig")
    }

    #[tokio::test]
    async fn whoami_reads_the_forwarded_token() {
        // Apps with extended identity propagation receive the token without `domino-username`.
        let request = Request::get("/api/whoami")
            .header(header::AUTHORIZATION, token_for("jane.doe"))
            .body(Body::empty())
            .unwrap();
        let body: Value = serde_json::from_str(&body_text(send(request).await).await).unwrap();
        assert_eq!(body, json!({ "username": "jane.doe", "source": "token" }));
    }

    #[tokio::test]
    async fn whoami_prefers_the_token_over_a_client_supplied_header() {
        let request = Request::get("/api/whoami")
            .header(header::AUTHORIZATION, token_for("jane.doe"))
            .header("domino-username", "someone.else")
            .body(Body::empty())
            .unwrap();
        let body: Value = serde_json::from_str(&body_text(send(request).await).await).unwrap();
        assert_eq!(body, json!({ "username": "jane.doe", "source": "token" }));
    }

    #[tokio::test]
    async fn index_has_only_relative_urls_and_escapes_input() {
        let request = Request::get("/")
            .header("domino-username", "<b>jane</b>")
            .body(Body::empty())
            .unwrap();
        let response = send(request).await;
        assert_eq!(response.status(), StatusCode::OK);
        let html = body_text(response).await;
        for absolute in ["href=\"/", "src=\"/", "action=\"/", "fetch(\"/"] {
            assert!(!html.contains(absolute), "root-absolute URL: {absolute}");
        }
        assert!(
            html.contains("&#60;b&#62;jane&#60;/b&#62;"),
            "askama escapes header text"
        );
    }

    #[tokio::test]
    async fn redirects_are_relative() {
        let response = send(Request::post("/refresh").body(Body::empty()).unwrap()).await;
        assert_eq!(response.status(), StatusCode::SEE_OTHER);
        assert_eq!(response.headers()[header::LOCATION], "./");
    }

    #[tokio::test]
    async fn serves_static_files() {
        let response = send(Request::get("/static/app.css").body(Body::empty()).unwrap()).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()[header::CONTENT_TYPE], "text/css");
    }

    #[tokio::test]
    async fn predict_without_model_settings_is_503() {
        let request = Request::post("/api/predict")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(r#"{"x": 1}"#))
            .unwrap();
        assert_eq!(
            send(request).await.status(),
            StatusCode::SERVICE_UNAVAILABLE
        );
    }
}
