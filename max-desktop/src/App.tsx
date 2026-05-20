/**
 * App.tsx — MAX v4.4
 * Orb UI: centered, draggable, full voice pipeline.
 */

import React, { useEffect, useState, useRef, useCallback } from "react";
import { listen }           from "@tauri-apps/api/event";
import { openUrl }          from "@tauri-apps/plugin-opener";
import { availableMonitors, getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { useBackend, BackendMessage, BackendStatus } from "./hooks/useBackend";
import { useVoice }         from "./hooks/useVoice";
import { start_listening_animation, stop_listening_animation } from "./overlayController";
import "./App.css";

const DRAG_THRESHOLD_MS         = 200;
const POSITION_SAVE_DEBOUNCE_MS = 300;
const TOAST_DURATION_MS         = 3_000;
const DBLCLICK_DELAY_MS         = 280;

type OrbState = "idle" | "listening" | "processing" | "speaking" | "error" | "offline";

const App: React.FC = () => {
  const mainWindowRef = useRef(getCurrentWindow());

  const [orbState, setOrbState]   = useState<OrbState>("idle");
  const [toastText, setToastText] = useState("");
  const [errorMsg,  setErrorMsg]  = useState("");

  const dragTimerRef     = useRef<number | null>(null);
  const dragStartedRef   = useRef(false);
  const saveTimerRef     = useRef<number | null>(null);
  const toastTimerRef    = useRef<number | null>(null);
  const errorTimerRef    = useRef<number | null>(null);
  const audioRef         = useRef<HTMLAudioElement | null>(null);
  const clickCountRef    = useRef(0);
  const clickTimerRef    = useRef<number | null>(null);
  const pointerDownTime  = useRef(0);

  useEffect(() => {
    const activeStates = ["listening", "processing", "speaking"];
    localStorage.setItem("max-overlay-state", orbState);
    if (activeStates.includes(orbState)) {
      start_listening_animation().catch(console.error);
    } else {
      stop_listening_animation().catch(console.error);
    }
  }, [orbState]);

  const showToast = useCallback((text: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastText(text);
    toastTimerRef.current = window.setTimeout(() => setToastText(""), TOAST_DURATION_MS);
  }, []);

  const showError = useCallback((msg: string) => {
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    setOrbState("error");
    setErrorMsg(msg);
    errorTimerRef.current = window.setTimeout(() => {
      setOrbState("idle");
      setErrorMsg("");
    }, 3_000);
  }, []);

  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
  }, []);

  const handleForceStop = useCallback(async () => {
    try {
      await fetch("http://localhost:8000/api/stop", { method: "POST" });
    } catch (err) {
      console.warn("Backend /api/stop unreachable:", err);
    }
    stopSpeaking();
    setOrbState("idle");
    showToast("🛑 Terminated");
  }, [stopSpeaking, showToast]);

  const playAudio = useCallback((rawBase64: string) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    setOrbState("speaking");
    const audio = new Audio(`data:audio/mp3;base64,${rawBase64}`);
    audioRef.current = audio;
    audio.onended = () => {
      audioRef.current = null;
      setOrbState("idle");
    };
    audio.onerror = () => {
      audioRef.current = null;
      setOrbState("idle");
    };
    audio.play().catch(() => {
      audioRef.current = null;
      setOrbState("idle");
    });
  }, []);

  const handleBackendMessage = useCallback((msg: BackendMessage) => {
    switch (msg.event) {
      case "greeting":
        if (msg.text) showToast(msg.text);
        break;
      case "transcript":
        break;
      case "response_text":
        if (msg.text) {
          // 🔴 FIX: Hide IMMEDIATELY on receiving the quit command!
          if (msg.text.includes("[ACTION:HIDE_ORB]")) {
            mainWindowRef.current.hide().catch(console.error);
          }
          const cleanText = msg.text.replace("[ACTION:HIDE_ORB]", "").trim();
          if (cleanText) showToast(cleanText);
        }
        break;
      case "audio_response":
        if (msg.audio) {
          playAudio(msg.audio);
        } else {
          setOrbState("idle");
        }
        break;
      case "error":
        showError(msg.message || "Something went wrong");
        break;
      default:
        break;
    }
  }, [showToast, showError, playAudio]);

  const handleStatusChange = useCallback((status: BackendStatus) => {
    if (status === "connected") {
      setOrbState(prev => prev === "offline" ? "idle" : prev);
    } else if (status === "offline" || status === "disconnected") {
      // 🔴 FIX: Only set to offline if the window is actually visible
      mainWindowRef.current.isVisible().then(visible => {
          if(visible) setOrbState("offline");
      });
    }
  }, []);

  const { send } = useBackend({ onMessage: handleBackendMessage, onStatusChange: handleStatusChange });

  const handleAudioReady = useCallback((base64: string) => {
    setOrbState("processing");
    if (!send({ type: "voice", audio: base64 })) {
      showError("Backend not connected");
    }
  }, [send, showError]);

  const { isRecording, startRecording, stopRecording } = useVoice({
    onAudioReady: handleAudioReady,
    onError: showError,
  });

  const handleSingleClick = useCallback(() => {
    if (orbState === "speaking" || orbState === "processing") {
      handleForceStop();
      return;
    }
    if (orbState === "offline") {
      showError("Backend offline");
      return;
    }
    if (isRecording) {
      stopRecording();
      setOrbState("processing");
      return;
    }
    startRecording();
    setOrbState("listening");
  }, [orbState, isRecording, startRecording, stopRecording, handleForceStop, showError]);

  const handleOpenFrontend = useCallback(async () => {
    try {
      await openUrl("http://localhost:5173");
    } catch (err) {
      showError("Could not open frontend");
    }
  }, [showError]);

  useEffect(() => {
    const restorePosition = async () => {
      const saved = localStorage.getItem("max-window-pos");
      if (!saved) return;
      try {
        const { x, y } = JSON.parse(saved) as { x: number; y: number };
        if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error("Invalid position");
        const [size, monitors] = await Promise.all([
          mainWindowRef.current.outerSize(),
          availableMonitors(),
        ]);
        const isOnScreen = monitors.some((monitor) => {
          const minX = monitor.position.x;
          const minY = monitor.position.y;
          const maxX = monitor.position.x + monitor.size.width - size.width;
          const maxY = monitor.position.y + monitor.size.height - size.height;
          return x >= minX && x <= maxX && y >= minY && y <= maxY;
        });
        if (!isOnScreen) {
          localStorage.removeItem("max-window-pos");
          return;
        }
        await mainWindowRef.current.setPosition(new PhysicalPosition(x, y));
      } catch {
        localStorage.removeItem("max-window-pos");
      }
    };
    void restorePosition();
  }, []);

  useEffect(() => {
    const unlistenPromise = listen("tauri://move", () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = window.setTimeout(async () => {
        try {
          const pos = await mainWindowRef.current.outerPosition();
          localStorage.setItem("max-window-pos", JSON.stringify({ x: pos.x, y: pos.y }));
        } catch {}
      }, POSITION_SAVE_DEBOUNCE_MS);
    });
    return () => {
      unlistenPromise.then(fn => fn());
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const unlistenPromise = listen("toggle-listening", async () => {
      await mainWindowRef.current.show();
      await mainWindowRef.current.setFocus();
      handleSingleClick();
    });
    return () => { unlistenPromise.then(fn => fn()); };
  }, [handleSingleClick]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    pointerDownTime.current = Date.now();
    dragStartedRef.current = false;
    dragTimerRef.current = window.setTimeout(async () => {
      try {
        await mainWindowRef.current.startDragging();
        dragStartedRef.current = true;
      } catch (err) {}
    }, DRAG_THRESHOLD_MS);
  }, []);

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    if (dragTimerRef.current !== null) {
      clearTimeout(dragTimerRef.current);
      dragTimerRef.current = null;
    }
    if (dragStartedRef.current) {
      dragStartedRef.current = false;
      return;
    }
    clickCountRef.current += 1;
    if (clickCountRef.current === 1) {
      clickTimerRef.current = window.setTimeout(() => {
        clickCountRef.current = 0;
        handleSingleClick();
      }, DBLCLICK_DELAY_MS);
    } else if (clickCountRef.current >= 2) {
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      clickCountRef.current = 0;
      handleOpenFrontend();
    }
  }, [handleSingleClick, handleOpenFrontend]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      if (dragTimerRef.current) clearTimeout(dragTimerRef.current);
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ""; }
    };
  }, []);

  return (
    <div className="orb-stage" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div
        className={`circle-icon ${orbState}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        role="button"
        aria-label="MAX orb"
      >
        <div className="orb-core" />
        <div className="orb-shell" />
        <div className="orb-ring" />
        <div className="orb-particles" />
      </div>
      {toastText && <div className="toast">{toastText}</div>}
    </div>
  );
};

export default App;