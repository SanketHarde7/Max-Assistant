// Path: max-desktop/src/App.tsx
// Use: Main component layout for Tauri desktop view.
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
import { LogicalSize, PhysicalPosition } from "@tauri-apps/api/dpi";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { useBackend, BackendMessage, BackendStatus } from "./hooks/useBackend";
import { useVoice }         from "./hooks/useVoice";
import { start_listening_animation, stop_listening_animation } from "./overlayController";
import "./App.css";

const DRAG_THRESHOLD_MS         = 200;
const POSITION_SAVE_DEBOUNCE_MS = 300;
const TOAST_DURATION_MS         = 3_000;
const DBLCLICK_DELAY_MS         = 280;
const TEXT_WINDOW_LABEL         = "overlay";
const TEXT_WINDOW_CONTENT_KEY   = "max-text-window-content";
const TEXT_WINDOW_VISIBLE_KEY   = "max-text-window-visible";

type OrbState = "idle" | "listening" | "processing" | "speaking" | "error" | "offline";

const App: React.FC = () => {
  const mainWindowRef = useRef(getCurrentWindow());
  const textWindowRef = useRef<WebviewWindow | null>(null);

  const [orbState, setOrbState]   = useState<OrbState>("idle");
  const [toastText, setToastText] = useState("");
  const [errorMsg,  setErrorMsg]  = useState("");
  const [continuousListening, setContinuousListening] = useState(true);
  const [isOrbHidden, setIsOrbHidden] = useState(false);

  // 🧠 WEB AUTOPILOT REGISTRATION STATE REFS
  const lastResearchFileRef = useRef<string | null>(null);
  const botBypassUrlRef = useRef<string | null>(null);
  const ignoreResponseRef = useRef<boolean>(false);
  const currentCommandIdRef = useRef<string>("");
  const lastSpeechEndRef     = useRef<number>(0);

  const dragTimerRef     = useRef<number | null>(null);
  const dragStartedRef   = useRef(false);
  const saveTimerRef     = useRef<number | null>(null);
  const toastTimerRef    = useRef<number | null>(null);
  const errorTimerRef    = useRef<number | null>(null);
  const islandTimerRef   = useRef<number | null>(null);
  const typewriterRef    = useRef<number | null>(null);
  const pendingHideRef   = useRef(false);
  const writingCompleteRef = useRef(false);
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
    setIsOrbHidden(localStorage.getItem("max-orb-hidden") === "1");
    if (activeStates.includes(orbState)) {
      start_listening_animation().catch(console.error);
    } else {
      stop_listening_animation().catch(console.error);
    }
    // Ensure overlay window stays on top
    mainWindowRef.current.setAlwaysOnTop(true).catch(() => {});
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

  const getTextWindow = useCallback(async () => {
    if (!textWindowRef.current) {
      textWindowRef.current = await WebviewWindow.getByLabel(TEXT_WINDOW_LABEL);
    }
    return textWindowRef.current;
  }, []);

  const hideTextWindow = useCallback(async (force: boolean = false) => {
    const pinned = localStorage.getItem('max-text-window-pinned') === '1';
    if (!force && pinned) {
      // Don't hide when pinned
      return;
    }
    localStorage.setItem("max-orb-hidden", "0");
    setIsOrbHidden(false);
    localStorage.setItem(TEXT_WINDOW_VISIBLE_KEY, "0");
    localStorage.removeItem(TEXT_WINDOW_CONTENT_KEY);
    localStorage.removeItem("max-text-window-position");
    // If writing is in progress and not forced, defer hide
    if (!force && typewriterRef.current) {
      pendingHideRef.current = true;
      return;
    }

    if (typewriterRef.current) {
      clearInterval(typewriterRef.current);
      typewriterRef.current = null;
    }
    if (islandTimerRef.current) {
      clearTimeout(islandTimerRef.current);
      islandTimerRef.current = null;
    }

    const textWindow = await getTextWindow();
    if (!textWindow) return;
    try {
      await textWindow.hide();
      pendingHideRef.current = false;
      writingCompleteRef.current = false;
    } catch {}
  }, [getTextWindow]);

  const showTextWindow = useCallback(async (text: string) => {
    if (islandTimerRef.current) {
      clearTimeout(islandTimerRef.current);
      islandTimerRef.current = null;
    }
    if (typewriterRef.current) {
      clearInterval(typewriterRef.current);
      typewriterRef.current = null;
    }

    // reset flags
    pendingHideRef.current = false;
    writingCompleteRef.current = false;
    localStorage.setItem("max-orb-hidden", "1");
    setIsOrbHidden(true);

    const textWindow = await getTextWindow();
    if (!textWindow) {
      showToast(text);
      return;
    }

    try {
      const [position, size] = await Promise.all([
        mainWindowRef.current.outerPosition(),
        mainWindowRef.current.outerSize(),
      ]);
      // Prioritize vertical growth (approx 60% vertical / 40% horizontal)
      const totalChars = Math.max(1, text.length);
      const preferredWidth = Math.ceil(Math.min(720, Math.max(260, Math.sqrt(totalChars) * 28)));
      const approxCharWidth = 8; // px
      const charsPerLine = Math.max(18, Math.floor(preferredWidth / approxCharWidth));
      const lines = Math.max(1, Math.ceil(totalChars / charsPerLine));
      const estimatedWidth = Math.max(260, Math.min(900, preferredWidth));
      const estimatedHeight = Math.max(140, Math.min(1200, 80 + lines * 30));

      // save anchor position closer to orb (smaller gap)
      const desiredX = position.x + size.width + 6;
      localStorage.setItem(
        "max-text-window-position",
        JSON.stringify({ x: desiredX, y: position.y })
      );
      const textWindow = await getTextWindow();
      if (textWindow) {
        await textWindow.setAlwaysOnTop(true).catch(() => {});
        await textWindow.setResizable(true).catch(() => {});
        await textWindow.setSize(new LogicalSize(estimatedWidth, estimatedHeight)).catch(() => {});
        await textWindow.setPosition(new PhysicalPosition(desiredX, position.y)).catch(() => {});
        await textWindow.show().catch(() => {});
      }
    } catch {}

    // Set the full text immediately to avoid Chromium background timer throttling
    localStorage.setItem(TEXT_WINDOW_VISIBLE_KEY, "1");
    localStorage.setItem(TEXT_WINDOW_CONTENT_KEY, text);
    writingCompleteRef.current = true;

    // Set auto-hide timer based on text length
    const closeDelay = Math.min(20000, Math.max(2500, text.length * 120));
    islandTimerRef.current = window.setTimeout(() => {
      void hideTextWindow();
    }, closeDelay);

    // If a hide was requested already, honor it
    if (pendingHideRef.current) {
      void hideTextWindow(true);
    }
  }, [getTextWindow, hideTextWindow, showToast]);



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
      console.log(`Exit triggered: ${reason}`);
      await invoke("exit_app");
    } catch (e) {
      console.error("Failed to invoke Rust exit_app:", e);
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
    if (msg.command_id && msg.command_id !== currentCommandIdRef.current) {
      console.log(`[App] Discarding stale backend message for ${msg.command_id}`);
      return;
    }

    switch (msg.event) {
      case "stale_discard":
        setOrbState("idle");
        showToast("⚠️ Discarded stale request");
        break;
      case "start_continuous_listening":
        setContinuousListening(true);
        showToast("🎙️ Ambient Listening ON");
        break;
      case "stop_continuous_listening":
        setContinuousListening(false);
        setOrbState("idle");
        showToast("🔇 Ambient Listening OFF");
        break;
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
        if (msg.command_id && currentCommandIdRef.current && msg.command_id !== currentCommandIdRef.current) {
          console.log(`Ignoring stale response_text for ${msg.command_id}`);
          break;
        }
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
          if (cleanText) {
            // Decide expansion: if more than one sentence, expand island, else toast only
            const sentences = cleanText.split(/[.!?]+\s*/).filter(Boolean).length;
            if (sentences > 1) {
              void showTextWindow(cleanText);
            } else {
              showToast(cleanText);
            }
          }
        }
        break;
      case "audio_response":
        if (msg.command_id && currentCommandIdRef.current && msg.command_id !== currentCommandIdRef.current) {
          console.log(`Ignoring stale audio_response for ${msg.command_id}`);
          break;
        }
        if (ignoreResponseRef.current) {
          ignoreResponseRef.current = false; // Reset
          setOrbState("idle");
          break;
        }
        if (msg.audio) {
          if (typewriterRef.current) {
            clearInterval(typewriterRef.current);
            typewriterRef.current = null;
          }
          if (islandTimerRef.current) {
            clearTimeout(islandTimerRef.current);
            islandTimerRef.current = null;
          }
          pendingHideRef.current = false;
          writingCompleteRef.current = true;
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
          if (typewriterRef.current) {
            clearInterval(typewriterRef.current);
            typewriterRef.current = null;
          }
          // Do not clear islandTimerRef here, let it fire naturally to auto-hide the window
          pendingHideRef.current = false;
          writingCompleteRef.current = true;
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
  }, [showToast, showError, playAudio, triggerHibernate, showTextWindow]);


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

  const handleForceStop = useCallback(async () => {
    try {
      await fetch("http://localhost:8000/api/stop", { method: "POST" });
    } catch (err) {
      console.warn("Backend /api/stop unreachable:", err);
    }
    void hideTextWindow(true);
    send({ type: "abort", command_id: currentCommandIdRef.current });
    stopSpeaking();
    setOrbState("idle");
    showToast("🛑 Terminated");
  }, [stopSpeaking, showToast, send, hideTextWindow]);

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

  const handleSpeechStart = useCallback(() => {
    if (Date.now() - lastSpeechEndRef.current < 800) {
      console.log("[App] VAD Speech started ignored (cooldown period)");
      return;
    }
    console.log("[App] VAD Speech started. Interrupting playback...");
    void hideTextWindow(true);
    stopSpeaking();
    if (currentCommandIdRef.current) {
      send({ type: "abort", command_id: currentCommandIdRef.current });
    }
    setOrbState("listening");
  }, [send, stopSpeaking, hideTextWindow]);

  const handleAudioReady = useCallback((base64: string) => {
    lastSpeechEndRef.current = Date.now();
    const commandId = `cmd_${Date.now()}`;
    currentCommandIdRef.current = commandId;
    setOrbState("processing");
    if (!send({ type: "voice", audio: base64, command_id: commandId, timestamp: Date.now() })) {
      showError("Backend not connected");
      setOrbState("idle");
    }
  }, [send, showError]);

  const { isRecording, startRecording, stopRecording, startContinuousListening, stopContinuousListening, updateJarvisState } = useVoice({
    onAudioReady: handleAudioReady,
    onError: showError,
    onSpeechStart: handleSpeechStart,
  });

  useEffect(() => {
    updateJarvisState(orbState);
  }, [orbState, updateJarvisState]);

  useEffect(() => {
    if (continuousListening) {
      startContinuousListening(orbState).catch(console.error);
    } else {
      stopContinuousListening();
    }
  }, [continuousListening, startContinuousListening, stopContinuousListening]);

  // Keep orb in 'listening' visual state during ambient mode when idle
  useEffect(() => {
    if (continuousListening && orbState === "idle") {
      setOrbState("listening");
    }
  }, [continuousListening, orbState]);

  const handleSingleClick = useCallback(() => {
    // When speaking or processing, tap = force stop MAX
    if (orbState === "speaking" || orbState === "processing") {
      handleForceStop();
      return;
    }
    if (orbState === "offline") {
      showError("Backend offline");
      return;
    }
    // If continuous listening is active, tap does nothing (VAD handles everything)
    if (continuousListening) {
      return;
    }
    // Manual push-to-talk fallback (only when continuous listening is OFF)
    if (isRecording) {
      stopRecording();
      setOrbState("processing");
      return;
    }
    startRecording();
    setOrbState("listening");
  }, [orbState, isRecording, continuousListening, startRecording, stopRecording, handleForceStop, showError]);

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
    <div className={`orb-stage ${isOrbHidden ? "orb-hidden" : ""}`}>
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