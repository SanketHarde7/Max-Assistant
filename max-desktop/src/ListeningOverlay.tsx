// Path: max-desktop/src/ListeningOverlay.tsx
// Use: Voice listening overlay window UI for Tauri.
import React from "react";
import "./ListeningOverlay.css";

type Props = {
  active: boolean;
};

export const ListeningOverlay: React.FC<Props> = ({ active }) => {
  if (!active) return null;
  return (
    <div className="listening-overlay" aria-hidden="true">
      <div className="animated-border" />
    </div>
  );
};
