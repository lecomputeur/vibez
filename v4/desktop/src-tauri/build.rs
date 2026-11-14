fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&[
        "alpha_update_state", "alpha_update_check", "alpha_update_allow",
        "language_get", "language_set", "panel_prefs_get", "panel_prefs_set", "chrome_panel", "chrome_snapshot", "web_navigate", "web_surface", "web_command", "web_choose_folder", "project_import_choose", "project_import_commit", "project_import_resolve", "project_details_action", "project_rules_edit", "project_open_folder", "app_command", "app_info", "app_choose_folder", "app_open_login", "app_save_export", "app_copy",
        "workspace_hide", "show_workspace", "workspace_command", "workspace_choose_folder", "workspace_open_login",
        "get_state", "navigate", "show_settings", "save_settings", "close_settings",
        "capture_screenshot", "show_screenshot", "screenshot_action", "get_diagnostics", "check_for_updates", "update_state", "update_action",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("Could not generate the preview's restricted command permissions");
}
