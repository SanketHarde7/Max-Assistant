/**
 * 🎙️ Voice Input Hook
 * Handles MediaRecorder API for mic recording with AnalyserNode
 * for real-time audio visualization data
 */
import { useState, useRef, useCallback, useEffect } from 'react'

export function useVoiceInput() {
  const [isRecording, setIsRecording] = useState(false)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const analyserRef = useRef(null)
  const streamRef = useRef(null)
  const audioContextRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAllTracks()
      if (audioContextRef.current?.state !== 'closed') {
        audioContextRef.current?.close()
      }
    }
  }, [])

  const stopAllTracks = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      })
      streamRef.current = stream

      // Create AudioContext + Analyser for visualization
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      audioContextRef.current = audioContext
      
      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.7
      source.connect(analyser)
      analyserRef.current = analyser

      // Setup MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.start(100) // collect data every 100ms
      setIsRecording(true)
    } catch (err) {
      console.error('Mic access error:', err)
      throw err
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (!mediaRecorderRef.current || !isRecording) return Promise.resolve(null)

    return new Promise((resolve) => {
      mediaRecorderRef.current.onstop = () => {
        stopAllTracks()
        
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        setIsRecording(false)

        // Close audio context
        if (audioContextRef.current?.state !== 'closed') {
          audioContextRef.current?.close()
        }
        analyserRef.current = null

        resolve(audioBlob)
      }

      mediaRecorderRef.current.stop()
    })
  }, [isRecording])

  return {
    startRecording,
    stopRecording,
    isRecording,
    analyserNode: analyserRef.current,
  }
}