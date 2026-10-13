# extension_manifest.json and official installs

Domino-built Extensions (AutoML Studio, Clinical Data Explorer, Auto Model Documentation) are installed from **Admin panel > Extensions > Manage Domino-official Extensions** by a SysAdmin or CloudAdmin (https://docs.domino.ai/cloud/platform-capabilities/features/extensions/install-domino-official-extensions). The installer reads `extension_manifest.json` from a GitHub release and creates four managed entities in order: Project, Compute Environment, App, Extension. It needs platform egress to GitHub, shows per-step progress and logs, and supports retry (from the failed step or clean), cancel and uninstall.

- Upgrades update the managed entities in place; the environment is rebuilt only if it changed.
- Downgrades are not supported: uninstall, then install the older version.
- Do not edit the managed Project, Compute Environment, App or Extension by hand; enable or disable from the Extensions tab only.
- A manually created Extension cannot become Domino Official; the designation comes only from the installer.
- Fixed names (Project name, App vanity URL) can collide with existing resources; resolve the conflict and retry.

## Manifest shape

`ExtensionManifestV1` requires `manifestSchemaVersion` (integer `1`), `project`, `app` and `extension`. Fields:

| Section | Fields |
|---|---|
| `project` | `name`, `description`, `visibility`, `isRestricted` |
| `app` | `computeEnvironment` (`type` `standard`, or `custom` with `customEnvironment.name`, `dockerfilePath`, `baseImage`, `autoCompatibleWithDomino`, `visibility`, `buildArgs`), `appName`, `appDescription`, `appVersionDescription`, `vanityUrl`, `entryPoint`, `visibility`, `enableDeepLinking`, `discoverable`, `mountDatasets`, `mountNetAppVolumes`, `externalVolumeMounts`, `hardwareTierIdSuggestion`, `autoscalingSpec` |
| `extension` | `name`, `description`, `enabled`, `uiMountPointTypeConfigs` (same shape as the Extensions API; `urlConfig.route` may be `null`) |

Copy from a real manifest rather than inventing one (`extension_manifest.json` at the repository root of each release tag):

- https://github.com/dominodatalab/AutoML_Extension
- https://github.com/dominodatalab/clinical-data-explorer
- https://github.com/dominodatalab/AutoDocumentation_Extension

**Deep linking vs iframe:** an App with deep linking on is never rendered in an iframe; the iframe setting applies only when deep linking is off, and deep linking needs `SecureIdentityPropagationToAppsEnabled`. Keep the manifest's `enableDeepLinking`, the App's deployment settings and any start overrides consistent.

## API analogs

`GET /api/extensions/beta/official-install-menu` lists the catalog and installable versions; `POST /api/extensions/beta/official-installs` starts an install; `GET .../official-installs/{id}` returns status, steps and logs; `POST .../{id}/retry`, `.../cancel` and `.../uninstall` mirror the Admin panel actions; `GET .../official-installs/{installId}/snapshots/{snapshotId}/liveDiff` reports drift between the installed configuration and the live entities. Route details: [API-EXTENSIONS.md](./API-EXTENSIONS.md).
