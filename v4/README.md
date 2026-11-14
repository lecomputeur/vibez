# VibeZ V4

VibeZ V4 is a desktop client for Mistral's web conversations (Work and Code) that adds local project folders. You link a folder on your computer to a Mistral project or conversation, browse its files in the side panel and review every proposed change before it is saved. It is a Rust/Tauri 2 app with a Python engine for the local file connector.

V4 is in open beta. It installs next to VibeZ 3 with its own app identity (`nl.lecomputeur.vibez4.alpha`), profile, settings and update channel, and never changes a VibeZ 3 installation. The VibeZ 3 source is in [`../desktop/`](../desktop/).

Download the current version from the [releases](https://github.com/lecomputeur/vibez/releases); contribution guidelines are in [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## Layout

| Path | What it is |
|---|---|
| `desktop/src-tauri/` | The app: Rust sources (`src/standalone.rs` is the entry point of the `vibez4-alpha` binary), scripts injected into the Mistral page (`src/*.js`), Tauri configuration and capabilities |
| `desktop/scripts/` | `prepare.cjs` builds `desktop/dist` and the generated translation catalogs |
| `standalone-ui/` | Toolbar, side panel and settings windows |
| `backend/` | Python engine: the local MCP file connector (`web_connector.py`), file access (`capfs.py`), document readers and writers |
| `desktop/standalone-tests/`, `tests/standalone/` | Node and Python tests |
| `management/` | Version and release records (`release.json`), the source allowlist (`source-files.json`) |
| `tools/` | Packaging, update feeds, release and live self-test tools |
| `packaging/` | Linux packaging and the native CI workflow template |

## Build and test

Requirements: Rust stable, Node.js 22, Python 3.12 or newer. On Debian or Ubuntu also:

```sh
sudo apt install build-essential pkg-config libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev libssl-dev
```

From this folder (`v4/`):

```sh
cd desktop && npm ci --ignore-scripts && node scripts/prepare.cjs
node --test standalone-tests/*.test.cjs
cd src-tauri && cargo test --locked --bin vibez4-alpha
cargo build --release --locked
cd ../.. && python3 -m unittest discover -s tests/standalone
python3 -m unittest discover -s management -p 'test_*.py'
```

The pull-request workflow runs the same tests on Linux. Tests never need a Mistral account; only `tools/live-work-self-test.py` drives a real signed-in Mistral session, with test projects the maintainer configures in an untracked `tools/live-work-self-test.local.json`.

## Adding a file

Source files are allow-listed. A new source file must be added to `management/source-files.json` and to the allowlist in `.gitignore`; otherwise it is left out of builds and releases.

## Releases and signing

Releases are built and signed by the maintainer with `tools/release-alpha.py` (version bump, frozen source, native CI, Linux packages, signed update feeds, draft prerelease). Signing keys, notarization credentials and the update-feed key are never in this repository; a pull request never needs them. VibeZ 3 releases are not affected by V4 releases: the VibeZ 3 updater only accepts 3.x versions.

## MCP protocol versions

Mistral talks to the local file connector over the Model Context Protocol. The connector is a *dual-era* server (see the comment above `VERSIONS` in [`backend/web_connector.py`](backend/web_connector.py)):

- **Modern, stateless** — `2026-07-28`: no handshake, every request carries its version and client capabilities in `params._meta`, the `Mcp-Method` and `Mcp-Name` headers mirror the body, `server/discover` advertises what the server speaks, every result carries `resultType`.
- **Legacy, session based** — `2025-06-18`, `2025-03-26`, `2024-11-05`: an `initialize` handshake opens a session identified by `Mcp-Session-Id`.

Mistral started sending the modern revision on 10 November 2026 and falls back to the handshake when a server does not answer it. The link readiness check proves both routes through the tunnel before a connector is used. `python3 tools/check-mcp-versions.py` compares these versions with the published specification and writes the result to `management/mcp-versions.json`.

## License

MIT, see [`LICENSE`](LICENSE). Bundled third-party code keeps its own license (`backend/vendor/`, `desktop/src-tauri/vendor/wry/`).
