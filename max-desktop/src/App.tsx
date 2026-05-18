/**
 * App.tsx — MAX v4.4
 * Orb UI: centered, draggable, full voice pipeline.
 *
 * CLICK BEHAVIOR:
 * Single click (idle)      → start listening (auto-stops on silence)
 * Single click (listening) → force-stop recording, process immediately
 * Single click (speaking)  → STOP MAX (kill audio playback)
 * Single click (processing)→ ignored (wait for response)
 * Double click             → open real frontend in system browser
 * Long press + drag        → move the orb
 *
 * ORB STATES:
 * idle       → deep blue, slow rotation (default)
 * listening  → lighter blue, fast pulse (recording + VAD active)
 * processing → orange, energy swirl (audio sent, waiting for response)
 * speaking   → purple, wave pulse (TTS playing)
 * error      → red, shake (3s then idle)
 * offline    → gray, dim pulse (WS disconnected)
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

  // ── Rust Full Screen Border Trigger & LocalStorage Sync ──────────────────
  useEffect(() => {
    const activeStates = ["listening", "processing", "speaking"];

    // 1. Fail-proof state sharing using localStorage
    localStorage.setItem("max-overlay-state", orbState);

    // 2. Trigger Rust to show/hide window
    if (activeStates.includes(orbState)) {
      start_listening_animation().catch(console.error);
    } else {
      stop_listening_animation().catch(console.error);
    }
  }, [orbState]);

  // ── Toast (transparent text, no window resize) ──────────────────────────
  const showToast = useCallback((text: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastText(text);
    toastTimerRef.current = window.setTimeout(() => setToastText(""), TOAST_DURATION_MS);
  }, []);

  // ── Error ────────────────────────────────────────────────────────────────
  const showError = useCallback((msg: string) => {
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    setOrbState("error");
    setErrorMsg(msg);
    errorTimerRef.current = window.setTimeout(() => {
      setOrbState("idle");
      setErrorMsg("");
    }, 3_000);
  }, []);

  // ── Stop audio playback (kill MAX speaking) ─────────────────────────────
  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setOrbState("idle");
    showToast("⏹ Stopped");
  }, [showToast]);

  // ── Audio playback ───────────────────────────────────────────────────────
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

  // ── Backend messages ─────────────────────────────────────────────────────
  const handleBackendMessage = useCallback((msg: BackendMessage) => {
    switch (msg.event) {
      case "greeting":
        if (msg.text) showToast(msg.text);
        break;
      case "transcript":
        // STT done — still processing
        break;
      case "response_text":
        if (msg.text) showToast(msg.text);
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
      case "pong":
        break;
      default:
        break;
    }
  }, [showToast, showError, playAudio]);

  const handleStatusChange = useCallback((status: BackendStatus) => {
    if (status === "connected") {
      setOrbState(prev => prev === "offline" ? "idle" : prev);
    } else if (status === "offline" || status === "disconnected") {
      setOrbState("offline");
    }
  }, []);

  const { send } = useBackend({ onMessage: handleBackendMessage, onStatusChange: handleStatusChange });

  // ── Voice (with auto-silence detection) ──────────────────────────────────
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

  // ── Core action: handle single click logic ──────────────────────────────
  const handleSingleClick = useCallback(() => {
    // While speaking → STOP MAX
    if (orbState === "speaking") {
      stopSpeaking();
      return;
    }

    // While processing → ignore
    if (orbState === "processing") return;

    // While offline → show error
    if (orbState === "offline") {
      showError("Backend offline");
      return;
    }

    // While listening → force stop immediately
    if (isRecording) {
      stopRecording();
      setOrbState("processing");
      return;
    }

    // Idle / error → start listening
    startRecording();
    setOrbState("listening");
  }, [orbState, isRecording, startRecording, stopRecording, stopSpeaking, showError]);

  // ── Double-click: open real frontend ─────────────────────────────────────
  const handleOpenFrontend = useCallback(async () => {
    try {
      await openUrl("http://localhost:5173");
    } catch (err) {
      console.error("Failed to open frontend:", err);
      showError("Could not open frontend");
    }
  }, [showError]);

  // ── Position save / restore ──────────────────────────────────────────────
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
          if (monitors.length > 0) {
            const fallback = monitors[0];
            const minX = fallback.position.x;
            const minY = fallback.position.y;
            const maxX = fallback.position.x + fallback.size.width - size.width;
            const maxY = fallback.position.y + fallback.size.height - size.height;
            const safeX = Math.min(Math.max(x, minX), maxX);
            const safeY = Math.min(Math.max(y, minY), maxY);
            await mainWindowRef.current.setPosition(new PhysicalPosition(safeX, safeY));
          }
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

  // ── Global shortcut ──────────────────────────────────────────────────────
  useEffect(() => {
    const unlistenPromise = listen("toggle-listening", () => handleSingleClick());
    return () => { unlistenPromise.then(fn => fn()); };
  }, [handleSingleClick]);

  // ── Pointer events: unified click / double-click / drag ──────────────────
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);

    pointerDownTime.current = Date.now();
    dragStartedRef.current = false;

    // Start drag timer
    dragTimerRef.current = window.setTimeout(async () => {
      try {
        await mainWindowRef.current.startDragging();
        dragStartedRef.current = true;
      } catch (err) {
        console.error("startDragging failed:", err);
      }
    }, DRAG_THRESHOLD_MS);
  }, []);

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;

    // Clear drag timer
    if (dragTimerRef.current !== null) {
      clearTimeout(dragTimerRef.current);
      dragTimerRef.current = null;
    }

    // If drag happened, ignore the click
    if (dragStartedRef.current) {
      dragStartedRef.current = false;
      return;
    }

    // Quick tap — handle click counting for single vs double
    clickCountRef.current += 1;

    if (clickCountRef.current === 1) {
      // Wait to see if second click comes
      clickTimerRef.current = window.setTimeout(() => {
        clickCountRef.current = 0;
        // Single click
        handleSingleClick();
      }, DBLCLICK_DELAY_MS);
    } else if (clickCountRef.current >= 2) {
      // Double click
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      clickCountRef.current = 0;
      handleOpenFrontend();
    }
  }, [handleSingleClick, handleOpenFrontend]);

  // ── Sync orbState with isRecording (VAD auto-stop) ──────────────────────
  useEffect(() => {
    if (!isRecording && orbState === "listening") {
      // VAD auto-stopped → already transitioning to processing via onAudioReady
      // This is a safety fallback
    }
  }, [isRecording, orbState]);

  // ── Cleanup ──────────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      if (dragTimerRef.current) clearTimeout(dragTimerRef.current);
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ""; }
    };
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="orb-stage">
      <div
        className={`circle-icon ${orbState}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        role="button"
        aria-label="MAX orb"
        title={
          orbState === "offline"    ? "Backend offline — reconnecting..." :
          orbState === "listening"  ? "Listening... click to stop & send" :
          orbState === "processing" ? "Processing..." :
          orbState === "speaking"   ? "Click to stop speaking" :
          orbState === "error"      ? errorMsg :
          "Click to speak • Double-click to open • Drag to move"
        }
      >
        {/* Inner animation layers */}
        <div className="orb-core" />
        <div className="orb-shell" />
        <div className="orb-ring" />
        <div className="orb-particles" />
      </div>
      {toastText && (
        <div className="toast">{toastText}</div>
      )}
    </div>
  );
};

export default App;