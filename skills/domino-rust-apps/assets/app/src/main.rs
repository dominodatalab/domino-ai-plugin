use std::{env, net::SocketAddr};

use domino_rust_app::{AppState, app, shutdown_signal};
use tracing_subscriber::{filter::Targets, prelude::*};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Domino App logs are stdout. RUST_LOG takes a level or per-module levels
    // ("debug", "warn,domino_rust_app=debug"); anything else falls back to info.
    let filter = env::var("RUST_LOG")
        .ok()
        .and_then(|value| value.parse::<Targets>().ok())
        .unwrap_or_else(|| Targets::new().with_default(tracing::Level::INFO));
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_ansi(std::io::IsTerminal::is_terminal(&std::io::stdout())),
        )
        .with(filter)
        .init();

    // Domino reaches an App only on 0.0.0.0:8888; PORT lets a Workspace run it beside the IDE.
    let port = match env::var("PORT") {
        Ok(value) => value.parse::<u16>()?,
        Err(_) => 8888,
    };
    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!(%addr, prefix = env::var("DOMINO_RUN_HOST_PATH").unwrap_or_default(), "listening");

    axum::serve(listener, app(AppState::from_env()?))
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    tracing::info!("server stopped");
    Ok(())
}
