import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import App from "./App";
import { ListeningOverlayFull } from "./ListeningOverlayFull.tsx"; // Naya component

const appWindow = getCurrentWindow();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {/* Agar window ka naam 'overlay' hai toh premium border dikhao, warna normal Orb */}
    {appWindow.label === "overlay" ? <ListeningOverlayFull /> : <App />}
  </React.StrictMode>
);