//! HTTP clients that work behind corporate HTTP proxies and TLS inspection.
//!
//! Both clients use rustls with the ring provider and trust the operating system's certificate
//! store (`/etc/ssl/certs`, maintained by `update-ca-certificates`), so a corporate root CA
//! installed in the Compute Environment is trusted without code changes.

use std::time::Duration;

/// Errors from building the App's clients and database pool.
pub type BoxError = Box<dyn std::error::Error + Send + Sync>;

/// Installs ring as the TLS crypto provider. Call before building any client or database pool.
pub fn install_crypto_provider() {
    // Fails only when a provider is already installed, which is fine.
    let _ = rustls::crypto::ring::default_provider().install_default();
}

/// Client for calls that leave the cluster (model endpoints, external services). It honours
/// `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY`.
///
/// # Errors
///
/// Returns an error if the TLS configuration cannot be built.
pub fn external_client() -> Result<reqwest::Client, reqwest::Error> {
    builder().build()
}

/// Client for Domino's in-cluster services (`DOMINO_API_HOST`, `DOMINO_API_PROXY`). It never uses a
/// proxy, so a corporate `HTTPS_PROXY` cannot intercept calls that must stay inside the cluster.
///
/// # Errors
///
/// Returns an error if the TLS configuration cannot be built.
pub fn internal_client() -> Result<reqwest::Client, reqwest::Error> {
    builder().no_proxy().build()
}

fn builder() -> reqwest::ClientBuilder {
    install_crypto_provider();
    reqwest::Client::builder().timeout(Duration::from_mins(1))
}
