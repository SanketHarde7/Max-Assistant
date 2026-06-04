import React, { useCallback, useEffect, useRef, useState } from "react";
import { LogicalSize, PhysicalPosition } from "@tauri-apps/api/dpi";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./TextWindow.css";

const TEXT_WINDOW_CONTENT_KEY = "max-text-window-content";
const TEXT_WINDOW_VISIBLE_KEY = "max-text-window-visible";

const textWindow = getCurrentWindow();

function readTextWindowState() {
  return {
    visible: localStorage.getItem(TEXT_WINDOW_VISIBLE_KEY) === "1",
    text: localStorage.getItem(TEXT_WINDOW_CONTENT_KEY) || "",
  };
}

function estimateWindowSize(text: string) {
  const lines = text.split(/\r?\n/);
  const longestLine = lines.reduce((max, line) => Math.max(max, line.length), 0);
  const lineCount = Math.max(1, lines.length);

  const width = Math.max(220, Math.ceil(180 + longestLine * 5.2));
  const height = Math.max(140, Math.ceil(110 + lineCount * 30 + Math.max(0, text.length - longestLine) * 0.22));

  return { width, height };
}

export const TextWindow: React.FC = () => {
  const [{ visible, text }, setWindowState] = useState(readTextWindowState);
  const resizeTimerRef = useRef<number | null>(null);

  const syncWindow = useCallback(async (nextVisible: boolean, nextText: string) => {
    if (nextVisible) {
      const { width, height } = estimateWindowSize(nextText);
      await textWindow.setAlwaysOnTop(true).catch(() => {});
      await textWindow.setResizable(true).catch(() => {});
      await textWindow.setSize(new LogicalSize(width, height)).catch(() => {});
      await textWindow.show().catch(() => {});
      await textWindow.setFocus().catch(() => {});
      return;
    }

    await textWindow.hide().catch(() => {});
  }, []);

  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";

    const refresh = () => setWindowState(readTextWindowState());
    const interval = window.setInterval(refresh, 120);
    window.addEventListener("storage", refresh);

    refresh();

    return () => {
      window.removeEventListener("storage", refresh);
      clearInterval(interval);
      if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    resizeTimerRef.current = window.setTimeout(() => {
      void syncWindow(visible, text);
    }, 16);
  }, [text, visible, syncWindow]);

  useEffect(() => {
    if (!visible) return;
    const position = localStorage.getItem("max-text-window-position");
    if (!position) return;
    try {
      const parsed = JSON.parse(position) as { x: number; y: number };
      if (Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) {
        void textWindow.setPosition(new PhysicalPosition(parsed.x, parsed.y)).catch(() => {});
      }
    } catch {}
  }, [visible]);

  if (!visible) {
    return null;
  }

  return (
    <div className="text-window-shell">
      <div className="text-window-panel">
        <div className="text-window-title">MAX</div>
        <div className="text-window-text" aria-live="polite">
          {text}
        </div>
      </div>
    </div>
  );
};

export default TextWindow;