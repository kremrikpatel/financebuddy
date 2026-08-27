//! Tauri shell for FinanceBuddy.
//!
//! The React frontend handles all app logic; this native process provides:
//! - OS keychain storage for secrets (refresh token, vault salt) — never plain files
//! - a place for deep links, single-instance, auto-update plumbing later

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            secure_store_set,
            secure_store_get,
            secure_store_delete,
        ])
        .run(tauri::generate_context!())
        .expect("error while running FinanceBuddy");
}

fn service_name(app: &tauri::AppHandle) -> String {
    format!("financebuddy.{}", app.package_info().name)
}

/// Store a secret in the OS keychain (Windows Credential Manager / Keychain / Secret Service).
#[tauri::command]
fn secure_store_set(app: tauri::AppHandle, key: String, value: String) -> Result<(), String> {
    let entry = keyring::Entry::new(&service_name(&app), &key).map_err(|e| e.to_string())?;
    entry.set_password(&value).map_err(|e| e.to_string())
}

#[tauri::command]
fn secure_store_get(app: tauri::AppHandle, key: String) -> Result<Option<String>, String> {
    let entry = keyring::Entry::new(&service_name(&app), &key).map_err(|e| e.to_string())?;
    match entry.get_password() {
        Ok(v) => Ok(Some(v)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn secure_store_delete(app: tauri::AppHandle, key: String) -> Result<(), String> {
    let entry = keyring::Entry::new(&service_name(&app), &key).map_err(|e| e.to_string())?;
    match entry.delete_credential() {
        Ok(_) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
