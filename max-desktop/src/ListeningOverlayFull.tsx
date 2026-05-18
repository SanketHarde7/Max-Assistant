import React, { useEffect, useState } from "react";
import "./ListeningOverlayFull.css";

export const ListeningOverlayFull: React.FC = () => {
  const [overlayState, setOverlayState] = useState(() => {
    return localStorage.getItem("max-overlay-state") || "idle";
  });

  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";

    // 1. Storage Listener (fires when App.tsx changes state)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === "max-overlay-state" && e.newValue) {
        setOverlayState(e.newValue);
      }
    };
    window.addEventListener("storage", handleStorageChange);

    // 2. Fallback Polling (Catches the exact millisecond if storage event is slightly delayed)
    const interval = setInterval(() => {
      const current = localStorage.getItem("max-overlay-state") || "idle";
      setOverlayState((prev) => {
        if (prev !== current) return current;
        return prev;
      });
    }, 100);

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="gas-overlay-container" aria-hidden="true">
      
      {/* 1. LISTENING THEME (Blue / Cyan Family) */}
      <div className={`theme-layer ${overlayState === "listening" ? "active" : ""}`}>
        <div className="gas-edge gas-top theme-listening" />
        <div className="gas-edge gas-bottom theme-listening" />
        <div className="gas-edge gas-left theme-listening" />
        <div className="gas-edge gas-right theme-listening" />
      </div>

      {/* 2. PROCESSING THEME (Orange / Warm Amber Family) */}
      <div className={`theme-layer ${overlayState === "processing" ? "active" : ""}`}>
        <div className="gas-edge gas-top theme-processing" />
        <div className="gas-edge gas-bottom theme-processing" />
        <div className="gas-edge gas-left theme-processing" />
        <div className="gas-edge gas-right theme-processing" />
      </div>

      {/* 3. SPEAKING THEME (Purple / Pink / Violet Family) */}
      <div className={`theme-layer ${overlayState === "speaking" ? "active" : ""}`}>
        <div className="gas-edge gas-top theme-speaking" />
        <div className="gas-edge gas-bottom theme-speaking" />
        <div className="gas-edge gas-left theme-speaking" />
        <div className="gas-edge gas-right theme-speaking" />
      </div>
      
      <div className="ambient-screen-glow" />
    </div>
  );
};