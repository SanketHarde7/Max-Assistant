/**
 * App.tsx — MAX v4.9 (Merged Health & Autopilot Follow-ups)
 * Orb UI: centered, draggable, full voice pipeline.
 *
 * CLICK BEHAVIOR:
 * Single click (idle)      → start listening (auto-stops on silence)
 * Single click (listening) → force-stop recording, process immediately
 * Single click (speaking)  → STOP MAX (kill audio playback & abort)
 * Single click (processing)→ STOP MAX (abort backend request)
 * Double click             → open real frontend in system browser
 * Long press + drag        → move the orb
 */

import React, { useEffect, useState, useRef, useCallback } from "react";
import { listen }           from "@tauri-apps/api/event";
import { invoke }           from "@tauri-apps/api/core"; // Rust API import
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

  // 🧠 WEB AUTOPILOT REGISTRATION STATE REFS
  const lastResearchFileRef = useRef<string | null>(null);
  const botBypassUrlRef = useRef<string | null>(null);
  const ignoreResponseRef = useRef<boolean>(false);

  const dragTimerRef     = useRef<number | null>(null);
  const dragStartedRef   = useRef(false);
  const saveTimerRef     = useRef<number | null>(null);
  const toastTimerRef    = useRef<number | null>(null);
  const errorTimerRef    = useRef<number | null>(null);
  const audioRef         = useRef<HTMLAudioElement | null>(null);
  const clickCountRef    = useRef(0);
  const clickTimerRef    = useRef<number | null>(null);
  const pointerDownTime  = useRef(0);

  const hibernateTimerRef = useRef<number | null>(null);
  const hibernateInFlightRef = useRef(false);
  const shouldHibernateRef = useRef(false);

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

  const triggerHibernate = useCallback(async (reason: string) => {
    if (hibernateInFlightRef.current) return;
    hibernateInFlightRef.current = true;

    if (hibernateTimerRef.current) {
      clearTimeout(hibernateTimerRef.current);
      hibernateTimerRef.current = null;
    }

    stopSpeaking();
    setOrbState("idle");

    try {
      console.log(`Hibernate triggered: ${reason}`);
      await invoke("hibernate_backend");
    } catch (e) {
      console.error("Failed to invoke Rust hibernate:", e);
    } finally {
      hibernateInFlightRef.current = false;
    }
  }, [stopSpeaking]);

  const playAudio = useCallback((rawBase64: string, hibernateAfter: boolean = false, isHealthAlert: boolean = false) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    setOrbState("speaking");
    const audio = new Audio(`data:audio/mp3;base64,${rawBase64}`);
    audioRef.current = audio;

    // 🔴 REDUCE VOLUME FOR HEALTH CHECK PAYLOADS
    if (isHealthAlert) {
      audio.volume = 0.35; // Soft ambient capacity
    } else {
      audio.volume = 1.0;  // Full volume conversation replies
    }
    
    audio.onended = async () => {
      audioRef.current = null;
      setOrbState("idle");
      
      if (hibernateAfter) {
        console.log("Audio finished. Handing over to Rust Dictator...");
        await triggerHibernate("audio-ended");
      }
    };
    
    audio.onerror = () => {
      audioRef.current = null;
      setOrbState("idle");
      if (hibernateAfter) {
        void triggerHibernate("audio-error");
      }
    };
    audio.play().catch(() => {
      audioRef.current = null;
      setOrbState("idle");
      if (hibernateAfter) {
        void triggerHibernate("audio-play-failed");
      }
    });
  }, [triggerHibernate]);

  const handleBackendMessage = useCallback((msg: BackendMessage) => {
    switch (msg.event) {
      case "greeting":
        if (msg.text) showToast(msg.text);
        break;
      case "transcript":
        // Call our dynamic follow-up interpreter loop before processing normal commands
        if (msg.text) {
          const intercepted = handleVoiceCommandInterpretation(msg.text);
          if (intercepted) {
             // Stop further backend pipeline processing since hook has captured the action
             break;
          }
        }
        break;
      case "response_text":
        if (ignoreResponseRef.current) {
          break;
        }
        if (msg.text) {
          if (msg.text.includes("[ACTION:HIBERNATE]")) {
            console.log("HIBERNATE TAG RECEIVED!");
            shouldHibernateRef.current = true;

            if (hibernateTimerRef.current) clearTimeout(hibernateTimerRef.current);
            hibernateTimerRef.current = window.setTimeout(() => {
              if (shouldHibernateRef.current) {
                void triggerHibernate("response-fallback");
                shouldHibernateRef.current = false;
              }
            }, 1200);
          }
          const cleanText = msg.text.replace("[ACTION:HIBERNATE]", "").trim();
          if (cleanText) showToast(cleanText);
        }
        break;
      case "audio_response":
        if (ignoreResponseRef.current) {
          ignoreResponseRef.current = false; // Reset
          setOrbState("idle");
          break;
        }
        if (msg.audio) {
          if (hibernateTimerRef.current) {
            clearTimeout(hibernateTimerRef.current);
            hibernateTimerRef.current = null;
          }

          // HEALTH ALERT CHECK (Volume adjustment flag validation)
          const isHealth = (msg as any).metadata?.type === "health_alert";

          // WEB AUTOPILOT ENGINE CACHE STATE STORAGE HOOKS
          if ((msg as any).metadata?.status === "file_saved") {
            lastResearchFileRef.current = (msg as any).metadata.file_path;
          }
          
          if ((msg as any).metadata?.status === "bot_detected") {
            botBypassUrlRef.current = (msg as any).metadata.url;
          }

          playAudio(msg.audio, shouldHibernateRef.current, isHealth);
          shouldHibernateRef.current = false; 
        } else {
          setOrbState("idle");
          if (shouldHibernateRef.current) {
            void triggerHibernate("no-audio");
            shouldHibernateRef.current = false;
          }
        }
        break;
      case "error":
        showError(msg.message || "Something went wrong");
        break;
      default:
        break;
    }
  }, [showToast, showError, playAudio, triggerHibernate]);

  const handleStatusChange = useCallback((status: BackendStatus) => {
    if (status === "connected") {
      setOrbState(prev => prev === "offline" ? "idle" : prev);
    } else if (status === "offline" || status === "disconnected") {
      mainWindowRef.current.isVisible().then(visible => {
          if (visible) setOrbState("offline");
      });
    }
  }, []);

  const { send } = useBackend({ onMessage: handleBackendMessage, onStatusChange: handleStatusChange });

  // Smart interception loop for conversational follow-ups (Yes/No handling)
  const handleVoiceCommandInterpretation = (userText: string): boolean => {
    // Standard JS trim handles whitespace cleanup safely without custom .strip extensions
    const text = userText.toLowerCase().trim();
    
    // Check if we have a saved research file path and user wants to open it
    if ((text.includes("yes") || text.includes("open") || text.includes("kholo") || text.includes("haan")) && lastResearchFileRef.current) {
        send({
            type: "execute_skill",
            skill: "open_app", 
            params: [lastResearchFileRef.current]
        } as any);
        lastResearchFileRef.current = null; // Token clear
        ignoreResponseRef.current = true;
        setOrbState("idle");
        return true; 
    }
    
    // Check if bot was detected and user wants to open it manually on screen
    if ((text.includes("yes") || text.includes("open") || text.includes("kholo") || text.includes("haan")) && botBypassUrlRef.current) {
        send({
            type: "execute_skill",
            skill: "web_open", 
            params: [botBypassUrlRef.current]
        } as any);
        botBypassUrlRef.current = null; // Token clear
        ignoreResponseRef.current = true;
        setOrbState("idle");
        return true; 
    }

    return false; 
  };

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
      console.error("Failed to open frontend:", err);
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
      } catch (err) {
        console.error("startDragging failed:", err);
      }
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
    if (!isRecording && orbState === "listening") {
    }
  }, [isRecording, orbState]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      if (dragTimerRef.current) clearTimeout(dragTimerRef.current);
      if (hibernateTimerRef.current) clearTimeout(hibernateTimerRef.current);
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

      {toastText && (
        <div className="toast">{toastText}</div>
      )}
      {errorMsg && (
        <div className="toast error-toast">{errorMsg}</div>
      )}
    </div>
  );
};

export default App;