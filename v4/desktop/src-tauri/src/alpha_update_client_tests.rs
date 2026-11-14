//! Real updater verification and AppImage replacement, using disposable keys and inert bytes.
//! No visible runtime, app profile, production signing key or executable is used.
#![cfg(target_os = "linux")]
use super::*;
use base64::{engine::general_purpose::STANDARD, Engine};
use std::{fs, os::unix::fs::PermissionsExt, process::Command};
use tauri::test::{mock_builder, mock_context, noop_assets, MockRuntime};
use tauri_plugin_updater::{Error, Update, Updater};

struct Fixture {
    root: PathBuf,
    current: PathBuf,
    sentinel: PathBuf,
    payload: Vec<u8>,
    key: String,
    signature: String,
    unversioned: String,
    next: Version,
}
struct PrivateDirectory(PathBuf);
impl Drop for PrivateDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
impl Fixture {
    fn new() -> Self {
        let mut random = [0u8; 16];
        getrandom::fill(&mut random).unwrap();
        let root = std::env::temp_dir().join(format!(
            "vibez-alpha-native-update-{}",
            random
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>()
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let cleanup = PrivateDirectory(root.clone());
        let current = root.join("VibeZ-Alpha.AppImage");
        let sentinel = root.join("must-stay-A.AppImage");
        fs::write(&current, b"\x7fELF inert fixture A - never executed").unwrap();
        fs::set_permissions(&current, fs::Permissions::from_mode(0o750)).unwrap();
        fs::write(&sentinel, b"unrelated fixture - preserve").unwrap();
        let mut payload = b"\x7fELF inert fixture B - never executed".to_vec();
        payload.resize(128, 0);
        let file = root.join("candidate.AppImage");
        fs::write(&file, &payload).unwrap();
        let mut next = Version::parse(env!("CARGO_PKG_VERSION")).unwrap();
        // The next release of the same stage: alpha.N -> alpha.N+1, beta.N -> beta.N+1.
        let (stage, number) = next.pre.as_str().split_once('.').unwrap();
        let number = number.parse::<u32>().unwrap() + 1;
        next.pre = semver::Prerelease::new(&format!("{stage}.{number}")).unwrap();
        let cli =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../node_modules/@tauri-apps/cli/tauri.js");
        let private = root.join("throwaway.key");
        run_cli(
            &cli,
            &[
                "signer",
                "generate",
                "--ci",
                "--password",
                "",
                "--write-keys",
                private.to_str().unwrap(),
            ],
        );
        fs::set_permissions(&private, fs::Permissions::from_mode(0o600)).unwrap();
        run_cli(
            &cli,
            &[
                "signer",
                "sign",
                "--private-key-path",
                private.to_str().unwrap(),
                "--password",
                "",
                "--app-version",
                &next.to_string(),
                file.to_str().unwrap(),
            ],
        );
        let signature = fs::read_to_string(file.with_extension("AppImage.sig"))
            .unwrap()
            .trim()
            .to_string();
        let unsigned = root.join("unversioned.AppImage");
        fs::write(&unsigned, &payload).unwrap();
        run_cli(
            &cli,
            &[
                "signer",
                "sign",
                "--private-key-path",
                private.to_str().unwrap(),
                "--password",
                "",
                unsigned.to_str().unwrap(),
            ],
        );
        let unversioned = fs::read_to_string(unsigned.with_extension("AppImage.sig"))
            .unwrap()
            .trim()
            .to_string();
        let key = fs::read_to_string(private.with_extension("key.pub"))
            .unwrap()
            .trim()
            .to_string();
        // Remove the secret immediately; every subsequent operation uses only the independent public key.
        fs::remove_file(private).unwrap();
        std::mem::forget(cleanup);
        Self {
            root,
            current,
            sentinel,
            payload,
            key,
            signature,
            unversioned,
            next,
        }
    }
    fn updater(&self) -> (tauri::App<MockRuntime>, Updater) {
        let mut context = mock_context(noop_assets());
        context.package_info_mut().version = Version::parse(env!("CARGO_PKG_VERSION")).unwrap();
        let mut config: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(config["plugins"]["updater"]["requireSignedVersion"], true);
        assert_ne!(config["plugins"]["updater"]["allowDowngrades"], true);
        config["plugins"]["updater"]["pubkey"] = json!(self.key);
        context
            .config_mut()
            .plugins
            .0
            .insert("updater".into(), config["plugins"]["updater"].clone());
        let app = mock_builder()
            .plugin(tauri_plugin_updater::Builder::new().build())
            .build(context)
            .unwrap();
        let updater = app
            .updater_builder()
            .target("linux-x86_64-appimage")
            .executable_path(&self.current)
            .version_comparator(|current, release| newer(&current, &release.version))
            .no_proxy()
            .configure_client(|_| panic!("this offline fixture must never access the network"))
            .endpoints(vec![ENDPOINT.parse().unwrap()])
            .unwrap()
            .build()
            .unwrap();
        (app, updater)
    }
    fn manifest(&self) -> Value {
        json!({"version":self.next.to_string(),"platforms":{"linux-x86_64-appimage":{
  "url":format!("https://github.com/lecomputeur/vibez/releases/download/v{0}/VibeZ-{0}-Linux-x64.AppImage",self.next),"signature":self.signature}}})
    }
    fn restore(&self, updater: &Updater, raw: Value) -> Update {
        updater.restore_update(raw).unwrap().unwrap()
    }
    fn unchanged(&self) {
        assert_eq!(
            fs::read(&self.current).unwrap(),
            b"\x7fELF inert fixture A - never executed"
        );
        assert_eq!(
            fs::read(&self.sentinel).unwrap(),
            b"unrelated fixture - preserve"
        );
    }
}
fn run_cli(cli: &Path, args: &[&str]) {
    // The CLI may print the freshly generated secret. Capture and discard all output, including errors.
    let output = Command::new("node")
        .arg(cli)
        .args(args)
        .env_remove("TAURI_SIGNING_PRIVATE_KEY")
        .env_remove("TAURI_SIGNING_PRIVATE_KEY_PATH")
        .env_remove("TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "disposable fixture signer failed (output intentionally withheld)"
    );
}

#[test]
fn signed_cache_roundtrip_replaces_only_the_explicit_private_appimage() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    let raw = fixture.manifest();
    let update = fixture.restore(&updater, raw.clone());
    validate_update(&update).unwrap();
    update.verify(&fixture.payload).unwrap();
    fixture.unchanged();
    let cache = fixture.root.join("cache");
    fs::create_dir(&cache).unwrap();
    private_write(&cache.join("package"), &fixture.payload).unwrap();
    private_write(
        &cache.join("release.json"),
        &serde_json::to_vec(&raw).unwrap(),
    )
    .unwrap();
    assert_eq!(
        fs::metadata(cache.join("package"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    let mut cached: Value =
        serde_json::from_slice(&fs::read(cache.join("release.json")).unwrap()).unwrap();
    // Cached metadata may not replace the runtime's verification key or executable destination.
    cached["extract_path"] = json!(fixture.sentinel);
    cached["config"] = json!({"pubkey":"untrusted-key","requireSignedVersion":false});
    let restored = fixture.restore(&updater, cached);
    validate_update(&restored).unwrap();
    assert_eq!(restored.current_version, env!("CARGO_PKG_VERSION"));
    assert_eq!(restored.target, "linux-x86_64-appimage");
    assert!(!matches!(
        tauri::utils::platform::bundle_type(),
        Some(tauri::utils::config::BundleType::Deb | tauri::utils::config::BundleType::Rpm)
    ));
    let bytes = fs::read(cache.join("package")).unwrap();
    restored.verify(&bytes).unwrap();
    restored.install(&bytes).unwrap();
    assert_eq!(fs::read(&fixture.current).unwrap(), fixture.payload);
    assert_eq!(
        fs::metadata(&fixture.current).unwrap().permissions().mode() & 0o777,
        0o750
    );
    assert_eq!(
        fs::read(&fixture.sentinel).unwrap(),
        b"unrelated fixture - preserve"
    );
}
#[test]
fn cryptographic_verification_rejects_changed_bytes_and_signatures_before_install() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    let update = fixture.restore(&updater, fixture.manifest());
    let mut changed = fixture.payload.clone();
    changed[30] ^= 1;
    assert!(update.verify(&changed).is_err());
    assert!(update.install(&changed).is_err());
    fixture.unchanged();
    let mut raw = fixture.manifest();
    let mut decoded = String::from_utf8(STANDARD.decode(&fixture.signature).unwrap()).unwrap();
    decoded = decoded.replace("candidate.AppImage", "forged-name.AppImage");
    assert_ne!(
        STANDARD.encode(&decoded),
        fixture.signature,
        "trusted comment tampering must actually change the signature document"
    );
    raw["platforms"]["linux-x86_64-appimage"]["signature"] = json!(STANDARD.encode(decoded));
    let forged = fixture.restore(&updater, raw);
    assert!(forged.verify(&fixture.payload).is_err());
    assert!(forged.install(&fixture.payload).is_err());
    fixture.unchanged();
}
#[test]
fn restored_package_must_be_signed_for_the_exact_announced_alpha_version() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    let mut raw = fixture.manifest();
    let mut later = fixture.next.clone();
    let (stage, number) = later.pre.as_str().split_once('.').unwrap();
    let number = number.parse::<u32>().unwrap() + 1;
    later.pre = semver::Prerelease::new(&format!("{stage}.{number}")).unwrap();
    raw["version"] = json!(later.to_string());
    raw["platforms"]["linux-x86_64-appimage"]["url"] = json!(format!(
        "https://github.com/lecomputeur/vibez/releases/download/v{0}/VibeZ-{0}-Linux-x64.AppImage",
        later
    ));
    let update = fixture.restore(&updater, raw);
    validate_update(&update).unwrap();
    assert!(matches!(
        update.verify(&fixture.payload),
        Err(Error::SignedVersionMismatch { .. })
    ));
    assert!(matches!(
        update.install(&fixture.payload),
        Err(Error::SignedVersionMismatch { .. })
    ));
    fixture.unchanged();
}
#[test]
fn unversioned_signature_cannot_disable_the_runtime_signed_version_requirement() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    let mut raw = fixture.manifest();
    raw["platforms"]["linux-x86_64-appimage"]["signature"] = json!(fixture.unversioned);
    raw["config"] = json!({"requireSignedVersion":false,"allowDowngrades":true});
    let update = fixture.restore(&updater, raw);
    assert!(matches!(
        update.verify(&fixture.payload),
        Err(Error::MissingSignedVersion)
    ));
    assert!(matches!(
        update.install(&fixture.payload),
        Err(Error::MissingSignedVersion)
    ));
    fixture.unchanged();
}
#[test]
fn restore_uses_production_alpha_comparator_and_exact_target() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    for version in [
        "3.0.10",
        "3.1.0",
        "4.0.0-test.999",
        "5.0.0-alpha.1",
        env!("CARGO_PKG_VERSION"),
        "4.0.0-alpha.1",
    ] {
        let mut raw = fixture.manifest();
        raw["version"] = json!(version);
        assert!(updater.restore_update(raw).unwrap().is_none(), "{version}");
    }
    let mut wrong = fixture.manifest();
    let target = wrong["platforms"]["linux-x86_64-appimage"].take();
    wrong["platforms"] = json!({"windows-x86_64-nsis":target});
    assert!(matches!(
        updater.restore_update(wrong),
        Err(Error::TargetNotFound(_))
    ));
    fixture.unchanged();
}
#[test]
fn production_url_policy_rejects_changed_origins_tags_names_and_url_extras() {
    let fixture = Fixture::new();
    let (_app, updater) = fixture.updater();
    let raw = fixture.manifest();
    let valid = raw["platforms"]["linux-x86_64-appimage"]["url"]
        .as_str()
        .unwrap();
    for url in [
        valid.replace("https:", "http:"),
        valid.replace("github.com", "evil.invalid"),
        valid.replace("lecomputeur/vibez/", "other/vibez/"),
        valid.replace("/download/v", "/download/stable-v"),
        valid.replace("/VibeZ-", "/Other-"),
        format!("{valid}?token=unexpected"),
        format!("{valid}#extra"),
        valid.replace("https://", "https://user:password@"),
    ] {
        let mut changed = raw.clone();
        changed["platforms"]["linux-x86_64-appimage"]["url"] = json!(url);
        let update = fixture.restore(&updater, changed);
        assert!(validate_update(&update).is_err(), "{url}");
    }
    fixture.unchanged();
}
