import { invoke } from "@tauri-apps/api/core";

export async function start_listening_animation() {
  await invoke("start_listening_animation");
}

export async function stop_listening_animation() {
  await invoke("stop_listening_animation");
}
