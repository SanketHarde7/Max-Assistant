#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;
use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WindowEvent,
};
use tauri_plugin_global_shortcut::{
    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x08000000;

struct AppState {
    backend_process: Mutex<Option<std::process::Child>>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            backend_process: Mutex::new(None),
        })
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let app_handle = app.handle();
            start_backend(app_handle.clone());

            let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyM);
            app_handle
                .global_shortcut()
                .on_shortcut(shortcut, |app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("toggle-listening", ());
                        }
                    }
                })
                .expect("Failed to register global shortcut");

            let tray_menu = Menu::new(app_handle)?;
            let open_item = MenuItem::with_id(app_handle, "open", "Wake Up MAX", true, None::<&str>)?;
            let settings_item = MenuItem::with_id(app_handle, "settings", "Settings", true, None::<&str>)?;
            let exit_item = MenuItem::with_id(app_handle, "exit", "Exit Completely", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app_handle)?;

            tray_menu.append_items(&[&open_item, &settings_item, &separator, &exit_item])?;

            // 🟢 FAIL-SAFE ICON LOADING: Ab app kabhi crash nahi hoga!
            let mut tray_builder = TrayIconBuilder::new()
                .menu(&tray_menu)
                .show_menu_on_left_click(false);

            if let Some(icon) = app.default_window_icon().cloned() {
                tray_builder = tray_builder.icon(icon);
            }

            let _tray = tray_builder
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                        ensure_backend_running(app.clone());
                    }
                    "settings" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("show-settings", ());
                        }
                    }
                    "exit" => {
                        let state: tauri::State<AppState> = app.state();
                        if let Some(mut child) = state.backend_process.lock().unwrap().take() {
                            let _ = child.kill();
                        }
                        std::process::exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let is_visible = window.is_visible().unwrap_or(false);
                            if !is_visible {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                        ensure_backend_running(app.clone());
                    }
                })
                .build(app_handle)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![exit_app, start_listening_animation, stop_listening_animation])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Prevent app from dying, just hide the window
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn ensure_backend_running(app_handle: tauri::AppHandle) {
    let state: tauri::State<AppState> = app_handle.state();
    let mut backend_lock = state.backend_process.lock().unwrap();
    
    let mut needs_restart = false;
    
    if let Some(child) = backend_lock.as_mut() {
        match child.try_wait() {
            Ok(Some(_status)) => needs_restart = true, 
            Ok(None) => { },
            Err(_) => needs_restart = true, 
        }
    } else {
        needs_restart = true; 
    }
    
    if needs_restart {
        *backend_lock = None;
        drop(backend_lock); 
        start_backend(app_handle);
    }
}

fn start_backend(app_handle: tauri::AppHandle) {
    std::thread::spawn(move || {
        let manifest_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| manifest_dir.to_path_buf());

        let backend_path = project_root.join("backend").join("main.py");
        if !backend_path.exists() {
            return;
        }

        #[cfg(target_os = "windows")]
        let python_cmd = project_root.join("backend").join(".venv").join("Scripts").join("python.exe");

        #[cfg(not(target_os = "windows"))]
        let python_cmd = project_root.join("backend").join(".venv").join("bin").join("python3");

        if !python_cmd.exists() {
            return;
        }

        #[allow(unused_mut)]
        let mut command = Command::new(python_cmd);
        command.arg(backend_path)
            .current_dir(&project_root)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null());

        #[cfg(target_os = "windows")]
        command.creation_flags(CREATE_NO_WINDOW);

        if let Ok(child) = command.spawn() {
            std::thread::sleep(std::time::Duration::from_secs(2));
            let state: tauri::State<AppState> = app_handle.state();
            *state.backend_process.lock().unwrap() = Some(child);
        }
    });
}

#[tauri::command]
fn exit_app(app_handle: tauri::AppHandle) {
    let state: tauri::State<AppState> = app_handle.state();
    if let Some(mut child) = state.backend_process.lock().unwrap().take() {
        let _ = child.kill();
    }
    std::process::exit(0);
}

#[tauri::command]
fn start_listening_animation(app_handle: tauri::AppHandle) {
    use tauri::Manager;
    if let Some(window) = app_handle.get_webview_window("overlay") {
        let _ = window.set_ignore_cursor_events(true);
        let _ = window.show();
    }
}

#[tauri::command]
fn stop_listening_animation(app_handle: tauri::AppHandle) {
    use tauri::Manager;
    if let Some(window) = app_handle.get_webview_window("overlay") {
        let _ = window.hide();
    }
}