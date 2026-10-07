fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&[
        "get_state", "navigate", "show_settings", "save_settings", "close_settings",
        "capture_screenshot", "show_screenshot", "screenshot_action", "get_diagnostics",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("Could not generate the preview's restricted command permissions");
}
