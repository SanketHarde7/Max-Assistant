// Path: max-desktop/src-tauri/src/main.rs
// Use: Launches the Tauri desktop wrapper application.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    max_desktop_lib::run();
}