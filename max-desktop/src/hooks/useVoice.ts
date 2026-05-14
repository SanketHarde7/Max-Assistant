/**
 * useVoice.ts — MAX v4.4
 * Microphone recording hook with automatic silence detection (VAD).
 *
 * BEHAVIOR (like Gemini):
 *   Click once → starts recording
 *   User speaks → keeps recording
 *   User goes silent for ~1.5s → auto-stops → fires onAudioReady
 *   Click again while recording → force-stop immediately
 *
 * SILENCE DETECTION:
 *   Uses Web Audio API AnalyserNode to compute RMS volume each frame.
 *   If RMS stays below SILENCE_THRESHOLD for SILENCE_DURATION_MS → auto-stop.
 *   Minimum recording of MIN_RECORD_MS to prevent false triggers.
 *   Maximum recording of MAX_RECORD_MS as safety cap.
 *
 * AUDIO FORMAT:
 *   Records as audio/webm;codecs=opus (Chromium default).
 *   Returns RAW base64 (no data URI prefix).
 */

import { useRef, useState, useCallback } from "react";

interface UseVoiceOptions {
  onAudioReady: (base64: string) => void;
  onError:      (message: string) => void;
}

const SILENCE_THRESHOLD   = 0.015;    // RMS below this = silence
const SILENCE_DURATION_MS = 1500;     // 1.5s of silence → auto-stop
const MIN_RECORD_MS       = 600;      // minimum recording length
const MAX_RECORD_MS       = 30_000;   // 30s safety cap

export function useVoice({ onAudioReady, onError }: UseVoiceOptions) {
  const [isRecording, setIsRecording]     = useState(false);
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);

  const mediaRecorderRef  = useRef<MediaRecorder | null>(null);
  const chunksRef         = useRef<Blob[]>([]);
  const streamRef         = useRef<MediaStream | null>(null);
  const audioContextRef   = useRef<AudioContext | null>(null);
  const analyserRef       = useRef<AnalyserNode | null>(null);
  const rafIdRef          = useRef<number | null>(null);
  const silenceStartRef   = useRef<number | null>(null);
  const recordStartRef    = useRef<number>(0);
  const maxTimerRef       = useRef<number | null>(null);
  const isStoppingRef     = useRef(false);

  // Stable refs so onstop closure doesn't capture stale callbacks
  const onAudioReadyRef = useRef(onAudioReady);
  const onErrorRef      = useRef(onError);
  onAudioReadyRef.current = onAudioReady;
  onErrorRef.current      = onError;

  const cleanup = useCallback(() => {
    // Cancel animation frame
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    // Cancel max timer
    if (maxTimerRef.current !== null) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    // Stop stream tracks
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    // Close audio context
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {});
    }
    audioContextRef.current = null;
    analyserRef.current = null;
    silenceStartRef.current = null;
    isStoppingRef.current = false;
  }, []);

  const doStop = useCallback(() => {
    if (isStoppingRef.current) return;
    isStoppingRef.current = true;

    // Cancel VAD loop
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    if (maxTimerRef.current !== null) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.requestData();
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    if (isRecording) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
      streamRef.current = stream;
      setHasPermission(true);

      // — Audio analysis setup —
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.3;
      source.connect(analyser);
      analyserRef.current = analyser;

      // — MediaRecorder setup —
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        cleanup();

        const blob   = new Blob(chunksRef.current, { type: mimeType });

        // If blob is too small, skip
        if (blob.size < 512) {
          return;
        }

        const reader = new FileReader();
        reader.onloadend = () => {
          const base64 = (reader.result as string).split(",")[1];
          onAudioReadyRef.current(base64);
        };
        reader.readAsDataURL(blob);
      };

      recorder.start(100); // collect chunks every 100ms
      recordStartRef.current = Date.now();
      silenceStartRef.current = null;
      isStoppingRef.current = false;
      setIsRecording(true);

      // — Safety cap: max 30s —
      maxTimerRef.current = window.setTimeout(() => {
        doStop();
      }, MAX_RECORD_MS);

      // — VAD loop: monitor volume for silence —
      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const vadLoop = () => {
        if (isStoppingRef.current) return;
        if (!analyserRef.current) return;

        analyserRef.current.getByteTimeDomainData(dataArray);

        // Compute RMS
        let sumSquares = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const val = (dataArray[i] - 128) / 128; // normalize to -1..1
          sumSquares += val * val;
        }
        const rms = Math.sqrt(sumSquares / dataArray.length);

        const now = Date.now();
        const elapsed = now - recordStartRef.current;

        if (rms < SILENCE_THRESHOLD) {
          // Silence detected
          if (silenceStartRef.current === null) {
            silenceStartRef.current = now;
          } else if (
            elapsed > MIN_RECORD_MS &&
            now - silenceStartRef.current >= SILENCE_DURATION_MS
          ) {
            // Enough silence after minimum recording → auto-stop
            doStop();
            return;
          }
        } else {
          // Voice detected — reset silence timer
          silenceStartRef.current = null;
        }

        rafIdRef.current = requestAnimationFrame(vadLoop);
      };

      rafIdRef.current = requestAnimationFrame(vadLoop);

    } catch (err) {
      setHasPermission(false);
      cleanup();
      onErrorRef.current(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission denied. Please allow mic access."
          : "Could not access microphone."
      );
    }
  }, [isRecording, cleanup, doStop]);

  const stopRecording = useCallback(() => {
    if (!isRecording || !mediaRecorderRef.current) return;
    doStop();
  }, [isRecording, doStop]);

  return { isRecording, hasPermission, startRecording, stopRecording };
}
