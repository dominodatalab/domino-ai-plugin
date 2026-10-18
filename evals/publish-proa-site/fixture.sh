#!/usr/bin/env bash
# A Proa site as `proa new site ... --template minimal` writes it (without Cargo.lock, tests and CI).
set -euo pipefail
mkdir -p .cargo src/components src/endpoints src/layouts src/pages public
cat > Cargo.toml <<'EOF'
[package]
name = "team-site"
version = "0.1.0"
edition = "2021"
rust-version = "1.93"

[dependencies]
anyhow = "1"
axum = "0.7.9"
dotenvy = "0.15"
proa_core = { version = "0.3.0" }
proa_framework_axum = { version = "0.3.0" }
proa_macros = { version = "0.3.0" }
proa_stream = { version = "0.3.0" }
serde = { version = "1", features = ["derive"] }
thiserror = "2"
tokio = { version = "1", features = ["macros", "rt-multi-thread", "signal"] }
tower-http = { version = "0.6", features = ["fs", "trace"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

[dev-dependencies]
http-body-util = "0.1"
tower = { version = "0.5", features = ["util"] }

[profile.release]
lto = "thin"
codegen-units = 1
EOF
cat > rust-toolchain.toml <<'EOF'
[toolchain]
channel = "1.93.0"
profile = "minimal"
components = ["rustfmt", "clippy"]
EOF
cat > proa.config.json <<'EOF'
{
  "$schema": "https://proa.so/schema/proa.config.json",
  "application": {
    "binary": "team-site",
    "kind": "site",
    "package": "team-site",
    "starter": "blank",
    "template": "minimal"
  },
  "build": {
    "assets": [],
    "before": [],
    "command": [
      "cargo",
      "build",
      "--release"
    ]
  },
  "database": {
    "driver": "none"
  },
  "deploy": {
    "provider": "none"
  },
  "dev": {
    "before": [],
    "command": [
      "cargo",
      "run"
    ],
    "watch": [
      "src",
      "styles",
      "migrations",
      "Cargo.toml",
      "build.rs",
      "proa.config.json",
      "proa.lock.json"
    ]
  },
  "paths": {
    "components": "src/components",
    "endpoints": "src/endpoints",
    "layouts": "src/layouts",
    "models": "src/models",
    "pages": "src/pages",
    "public": "public",
    "runtimeData": "data"
  },
  "registries": {
    "@proa": "https://ui.proa.so/r/{name}.json"
  },
  "representations": {
    "html": {
      "enabled": true
    },
    "markdown": {
      "enabled": false
    }
  },
  "styling": {
    "kind": "css",
    "output": "public/styles.css"
  },
  "tasks": {},
  "test": {
    "before": []
  },
  "ui": {
    "provider": "none"
  }
}
EOF
cat > proa.lock.json <<'EOF'
{
  "components": {},
  "scaffold": {
    "capabilities": [
      {
        "id": "base:site",
        "planVersion": 1
      },
      {
        "id": "server:axum",
        "planVersion": 1
      },
      {
        "id": "styling:css",
        "planVersion": 1
      },
      {
        "id": "starter:blank",
        "planVersion": 1
      }
    ],
    "cliVersion": "0.1.3",
    "release": "0.1.3"
  },
  "schemaVersion": 1
}
EOF
cat > build.rs <<'EOF'
fn main() {
    println!("cargo:rerun-if-changed=public");
}
EOF
cat > .cargo/config.toml <<'EOF'
[net]
git-fetch-with-cli = true
EOF
cat > .gitignore <<'EOF'
.env
/target/
/data/*.db
/data/*.db-shm
/data/*.db-wal
EOF
cat > .env.example <<'EOF'
PROA_HOST=127.0.0.1
PORT=3000
RUST_LOG=team-site=debug,tower_http=info
EOF
cat > src/main.rs <<'EOF'
use std::time::Duration;

use tokio::net::TcpListener;
use tracing_subscriber::EnvFilter;

mod app;
mod components;
mod config;
mod endpoints;
mod error;
mod layouts;
mod pages;
mod routes;
mod static_assets;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();
    let config = config::Config::from_env()?;
    let state = app::AppState;
    let app = routes::router(state, config.base_path);
    let listener = TcpListener::bind(config.address).await?;
    tracing::info!(address = %listener.local_addr()?, "Proa site listening");
    let _ = proa_framework_axum::serve(listener, app, Duration::from_secs(30)).await?;
    Ok(())
}
EOF
cat > src/app.rs <<'EOF'
#[derive(Clone, Default)]
pub struct AppState;
EOF
cat > src/config.rs <<'EOF'
use std::net::{IpAddr, SocketAddr};

pub struct Config {
    pub address: SocketAddr,
    pub base_path: proa_core::BasePath,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        dotenvy::dotenv().ok();
        let base_path =
            proa_core::BasePath::new(&std::env::var("PROA_BASE_PATH").unwrap_or_default())?;
        let host: IpAddr = std::env::var("PROA_HOST")
            .unwrap_or_else(|_| "127.0.0.1".to_string())
            .parse()?;
        let port = std::env::var("PORT")
            .unwrap_or_else(|_| "3000".to_string())
            .parse()?;
        Ok(Self {
            address: SocketAddr::new(host, port),
            base_path,
        })
    }
}
EOF
cat > src/error.rs <<'EOF'
use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
};

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("render failed: {0}")]
    Render(#[from] proa_core::WriteError),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        tracing::error!(error = %self, "request failed");
        (StatusCode::INTERNAL_SERVER_ERROR, "request failed").into_response()
    }
}
EOF
cat > src/routes.rs <<'EOF'
use std::{collections::HashMap, sync::Arc};

use axum::{routing::get, Router};
use proa_framework_axum::{router_from_spec, IslandManifest, Route, RouteContextLayer};
use tower_http::trace::TraceLayer;

use crate::{app::AppState, endpoints, pages, static_assets};

pub fn router(state: AppState, base_path: proa_core::BasePath) -> Router {
    let (router, metadata) = router_from_spec(vec![
        // proa:route-specs:start
        Route::endpoint("/", get(pages::home::handler)),
        // proa:route-specs:end
    ]);
    let manifest = Arc::new(IslandManifest {
        islands: HashMap::new(),
        assets: Default::default(),
        import_map: HashMap::new(),
        ssr_bundle: None,
    });
    router
        .route("/healthz", get(endpoints::health::live))
        .route("/readyz", get(endpoints::health::ready))
        // proa:explicit-routes:start
        // proa:explicit-routes:end
        .nest_service("/static", static_assets::service(base_path.clone()))
        .with_state(state)
        .merge(proa_framework_axum::rsjs_assets_router(&base_path))
        .layer(RouteContextLayer::new(manifest, metadata).with_base_path(base_path))
        .layer(TraceLayer::new_for_http())
}
EOF
cat > src/static_assets.rs <<'EOF'
use tower_http::services::ServeDir;

pub fn service(base_path: proa_core::BasePath) -> axum::Router {
    proa_framework_axum::base_path_assets(
        axum::Router::new()
            .fallback_service(ServeDir::new("public").append_index_html_on_directories(false)),
        base_path,
    )
}
EOF
cat > src/components/mod.rs <<'EOF'

EOF
cat > src/endpoints/mod.rs <<'EOF'
pub mod health;
EOF
cat > src/endpoints/health.rs <<'EOF'
use axum::Json;
use serde::Serialize;

#[derive(Serialize)]
pub struct StatusBody {
    status: &'static str,
}

pub async fn live() -> Json<StatusBody> {
    Json(StatusBody { status: "ok" })
}

pub async fn ready() -> Json<StatusBody> {
    Json(StatusBody { status: "ready" })
}
EOF
cat > src/layouts/mod.rs <<'EOF'
mod root;

pub use root::RootDocument;
EOF
cat > src/layouts/root.rs <<'EOF'
// proa:document-root
use std::future::Future;

use proa_core::{raw_text_ok, DataLoader, RenderOutcome, WebContext, WebRender, WriteError};
use proa_macros::html;

pub struct RootDocument<C> {
    pub title: &'static str,
    pub content: C,
}

impl<L, C> WebRender<L> for RootDocument<C>
where
    L: DataLoader,
    C: WebRender<L> + Send + 'static,
{
    fn render(
        self,
        cx: &mut WebContext<L>,
    ) -> RenderOutcome<impl Future<Output = Result<(), WriteError>>> {
        RenderOutcome::pending(async move {
            let RootDocument { title, content } = self;
            let favicon = cx.request().url("/static/favicon.svg");
            let stylesheet = cx.request().url("/static/styles.css");
            html! {
                <!DOCTYPE html>
                <html lang="en">
                    <head>
                        <meta charset="utf-8" />
                        <meta name="viewport" content="width=device-width, initial-scale=1" />
                        <meta name="color-scheme" content="dark" />
                        <title>{raw_text_ok(title)}</title>
                        <link rel="icon" href={favicon} />
                        <link rel="stylesheet" href={stylesheet} />
                    </head>
                    <body>{content}</body>
                </html>
            }
            .render(cx)
            .resolve()
            .await
        })
    }
}
EOF
cat > src/pages/mod.rs <<'EOF'
pub mod home;
EOF
cat > src/pages/home.rs <<'EOF'
use proa_core::{DataLoader, WebContext, WebRenderSync, WriteError};
use proa_macros::html_sync;

#[derive(Debug, Clone, Copy)]
pub struct HomePage;

impl<L: DataLoader> WebRenderSync<L> for HomePage {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <main class="blank-page">
                <h1>"Ready."</h1>
            </main>
        }
        .render(cx)
    }
}

use axum::response::IntoResponse;
use proa_framework_axum::RouteResponse;

use crate::{error::AppError, layouts::RootDocument};

pub async fn handler() -> Result<impl IntoResponse, AppError> {
    let html = RouteResponse::ssr_async(RootDocument {
        title: "Proa Domino",
        content: proa_core::to_async(HomePage),
    });
    Ok(html)
}
EOF
cat > public/styles.css <<'EOF'
:root{color-scheme:dark;--ink:#0b0b0c;--bone:#e5e1d6;--cyan:#3de1e8;--red:#ff3b30}*{box-sizing:border-box}body{margin:0;background:var(--ink);color:var(--bone);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}a{color:inherit}.topbar{height:58px;border-bottom:1px solid #ffffff2b;display:flex;align-items:center;justify-content:space-between;padding:0 4vw;font-size:11px;letter-spacing:.15em}.wordmark{font-size:22px;font-weight:900;color:var(--cyan);text-decoration:none}.hero{min-height:62vh;padding:8vh 4vw 6vh;display:grid;align-content:center;background-image:linear-gradient(#ffffff0a 1px,transparent 1px),linear-gradient(90deg,#ffffff0a 1px,transparent 1px);background-size:48px 48px}.kicker,.metric-label,.card-eyebrow{color:var(--cyan);font-size:11px;letter-spacing:.18em}.hero h1{max-width:1050px;margin:.4em 0 .25em;font-family:Arial,sans-serif;font-size:clamp(54px,8vw,124px);line-height:.84;text-transform:uppercase;letter-spacing:-.065em}.lede{max-width:760px;color:#aaa69e;font-family:Arial,sans-serif;font-size:20px;line-height:1.5}.badges{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.status-pill{display:inline-flex;align-items:center;gap:8px;border:1px solid #ffffff45;padding:8px 10px;font-size:10px;letter-spacing:.12em}.status-dot{width:7px;height:7px;border-radius:50%;background:var(--cyan);box-shadow:0 0 12px var(--cyan)}.hero-action{margin-top:28px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #ffffff2b}.metric-card{min-height:210px;padding:28px;border-right:1px solid #ffffff2b}.metric-card h2,.metric-value{font-family:Arial,sans-serif;font-size:40px;font-weight:800;margin:20px 0}.metric-note,.metric-card>p:last-child{color:#96938c;line-height:1.5}.receipt{position:sticky;bottom:0;display:flex;gap:28px;justify-content:flex-end;background:var(--bone);color:var(--ink);padding:12px 4vw;font-size:10px;letter-spacing:.08em}.receipt strong{color:#b44e00}@media(max-width:760px){.metrics{grid-template-columns:1fr}.hero h1{font-size:52px}.receipt{position:static;flex-wrap:wrap;justify-content:flex-start}}
EOF
cat > public/favicon.svg <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0b0b0c"/><path d="M13 46V18h22c10 0 16 5 16 14s-6 14-16 14H25v-8h10c3 0 5-2 5-6s-2-6-5-6H24v20z" fill="#3de1e8"/></svg>
EOF
cat > README.md <<'EOF'
# Team site

Created with `proa new site team-site --template minimal`. Code for our Git-based Domino Project.
EOF
