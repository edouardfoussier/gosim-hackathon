// Prevents an extra console window from appearing on Windows in --release
// builds. Harmless on macOS but kept so the source compiles cleanly when
// Edouard cross-checks on a Linux box.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;

use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent, WindowEvent,
};

mod child;

/// Shared state holding the OS handles for the two Python sidecars.
///
/// Wrapped in a `Mutex` so the setup thread (which spawns them) and the
/// `RunEvent::ExitRequested` handler (which kills them) don't race on
/// the `Child` value.
pub struct ChildProcesses {
    pub backend: Mutex<Option<std::process::Child>>,
    pub overlay: Mutex<Option<std::process::Child>>,
}

impl ChildProcesses {
    fn new() -> Self {
        Self {
            backend: Mutex::new(None),
            overlay: Mutex::new(None),
        }
    }
}

fn main() {
    let context = tauri::generate_context!();

    tauri::Builder::default()
        // Single-instance lock: a second double-click on Xiexie.app
        // re-focuses the existing window instead of spawning a duplicate
        // backend (which would EADDRINUSE on port 8787).
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main(app);
        }))
        .manage(ChildProcesses::new())
        .setup(|app| {
            // ── macOS: hide the dock icon, behave like a menu-bar app.
            // We do this both via Info.plist (LSUIElement, injected by
            // build-app.sh) and programmatically so the policy sticks
            // even on hot-reloads of the panel WebView.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            build_tray(app.handle())?;

            // Spawn the two Python sidecars on a worker thread so the
            // event loop isn't blocked by the 30-s health-check window
            // (`/health` polling — see `child::start_backend`).
            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                if let Err(err) = child::start_backend(&app_handle) {
                    eprintln!("[xiexie] backend launch failed: {err}");
                }
                if let Err(err) = child::start_overlay(&app_handle) {
                    eprintln!("[xiexie] overlay launch failed: {err}");
                }
            });

            Ok(())
        })
        .build(context)
        .expect("error while building Xiexie")
        .run(|app, event| {
            match event {
                // App quit (Cmd-Q, tray "Quit", or system shutdown):
                // SIGTERM both children, wait up to 5 s each, SIGKILL.
                RunEvent::ExitRequested { .. } => {
                    kill_children(app);
                }
                // Closing the panel window via the macOS red dot just
                // hides it — the tray icon is the source of truth for
                // app lifecycle, mirroring Clicky and Raycast.
                RunEvent::WindowEvent {
                    event: WindowEvent::CloseRequested { api, .. },
                    label,
                    ..
                } => {
                    if label == "main" {
                        api.prevent_close();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.hide();
                        }
                    }
                }
                _ => {}
            }
        });
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItemBuilder::with_id("show", "Show Xiexie").build(app)?;
    let hide = MenuItemBuilder::with_id("hide", "Hide").build(app)?;
    let separator_a = PredefinedMenuItem::separator(app)?;
    let reveal = MenuItemBuilder::with_id("reveal", "Reveal data folder…").build(app)?;
    let separator_b = PredefinedMenuItem::separator(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Quit Xiexie").build(app)?;

    let menu = MenuBuilder::new(app)
        .items(&[&show, &hide, &separator_a, &reveal, &separator_b, &quit])
        .build()?;

    // The tray glyph is bundled at compile time — `include_bytes!` reads
    // it relative to the source file, so the path is `../icons/tray.png`
    // (i.e. `desktop/src-tauri/icons/tray.png`).
    let tray_png = include_bytes!("../icons/tray.png");
    let icon = Image::from_bytes(tray_png).expect("tray icon must be valid PNG");

    TrayIconBuilder::with_id("xiexie")
        .icon(icon)
        // ``icon_as_template = true`` makes macOS auto-tint the silhouette
        // for both light- and dark-mode menu bars. Our ``make-icons.py``
        // produces a pure-black mask suited to that pipeline.
        .icon_as_template(true)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main(app),
            "hide" => hide_main(app),
            "reveal" => reveal_data_folder(app),
            "quit" => {
                kill_children(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // Left-click toggles the panel; the menu is reserved for
            // right-click (so left-click can be a low-friction "peek"
            // gesture, matching Clicky's UX).
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                toggle_main(app);
            }
        })
        .build(app)?;

    Ok(())
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn hide_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

fn toggle_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

fn reveal_data_folder(app: &AppHandle) {
    let dir = data_folder(app);
    if let Err(err) = std::fs::create_dir_all(&dir) {
        eprintln!("[xiexie] mkdir {} failed: {err}", dir.display());
    }
    let _ = Command::new("/usr/bin/open").arg(&dir).status();
}

/// Long-term memory location: `~/Library/Application Support/ai.xiexie.app/data`.
///
/// We deliberately don't reuse the dev-time `data/` folder at the repo
/// root — a packaged .app shouldn't write inside its own bundle (read-
/// only on Gatekeeper-translocated launches). The Python backend reads
/// `XIEXIE_DATA_DIR` (set in `child::start_backend`) so it lands here.
fn data_folder(app: &AppHandle) -> PathBuf {
    if let Ok(dir) = app.path().app_data_dir() {
        return dir.join("data");
    }
    // Fallback: ``$HOME/Library/Application Support/ai.xiexie.app/data``
    if let Some(home) = dirs_home() {
        return home
            .join("Library/Application Support/ai.xiexie.app/data");
    }
    PathBuf::from("./xiexie-data")
}

fn dirs_home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

fn kill_children(app: &AppHandle) {
    let state = app.state::<ChildProcesses>();
    child::shutdown(&state.backend, "backend");
    child::shutdown(&state.overlay, "overlay");
}
