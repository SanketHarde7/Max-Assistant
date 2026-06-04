import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import App from "./App";
import { TextWindow } from "./TextWindow";

const appWindow = getCurrentWindow();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {appWindow.label === "overlay" ? <TextWindow /> : <App />}
  </React.StrictMode>
);