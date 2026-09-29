//! Sky Towers desktop shell (spec §11): a thin window over the local service at http://127.0.0.1:8471,
//! a tray (فتح · نسخة احتياطية الآن · خروج), autostart and native notifications. The backend is an
//! independent Windows service; this shell starts and monitors nothing. Rust stays minimal: one command
//! opens a folder (the service log from the fallback page).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WindowEvent,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_opener::OpenerExt;

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// «فتح سجل الأخطاء» on the fallback page: opens `%ProgramData%\SkyTowers\logs` — that folder only. It took any
/// path before, and opening a path to a program runs it (review 2026-09-29, C-12).
#[tauri::command]
fn open_folder(app: AppHandle) -> Result<(), String> {
    let base = std::env::var("ProgramData").unwrap_or_else(|_| String::from("C:\\ProgramData"));
    let folder = format!("{base}\\SkyTowers\\logs");
    app.opener().open_path(folder, None::<&str>).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--hidden"])))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![open_folder])
        .setup(|app| {
            // Autostart at Windows sign-in (spec §11); started that way the window waits in the tray.
            let _ = app.autolaunch().enable();
            if std::env::args().any(|arg| arg == "--hidden") {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }

            let open = MenuItem::with_id(app, "open", "فتح", true, None::<&str>)?;
            let backup = MenuItem::with_id(app, "backup", "نسخة احتياطية الآن", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "خروج", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &backup, &quit])?;
            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().cloned().expect("bundle icon"))
                .tooltip("Sky Towers")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main(app),
                    // The signed-in page runs the backup with its own session (web/src/lib/desktop.ts).
                    "backup" => {
                        show_main(app);
                        let _ = app.emit("tray-backup", ());
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        // The close button hides to the tray; the page keeps polling, so notifications still arrive.
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Sky Towers");
}
