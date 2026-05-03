/**
 * 🔊 Audio Player Hook
 * Handles TTS audio playback with proper data URI format
 * and AudioContext AnalyserNode for reactive visuals
 */
import { useState, useRef, useCallback } from 'react'

export function useAudioPlayer() {
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef(null)
  const queueRef = useRef([])

  /**
   * Play base64 audio data.
   * @param {string} base64Audio - Raw base64 string (no prefix)
   * @param {Function} onEnd - Callback when playback ends
   */
  const playAudio = useCallback((base64Audio, onEnd) => {
    if (!base64Audio) {
      onEnd?.()
      return
    }

    // If already playing, queue
    if (isPlaying) {
      queueRef.current.push({ base64Audio, onEnd })
      return
    }

    setIsPlaying(true)

    // Proper data URI format
    const dataUri = `data:audio/mpeg;base64,${base64Audio}`
    const audio = new Audio(dataUri)
    audioRef.current = audio

    audio.onended = () => {
      setIsPlaying(false)
      audioRef.current = null
      onEnd?.()

      // Play next in queue
      if (queueRef.current.length > 0) {
        const next = queueRef.current.shift()
        playAudio(next.base64Audio, next.onEnd)
      }
    }

    audio.onerror = (err) => {
      console.error('Audio playback error:', err)
      setIsPlaying(false)
      audioRef.current = null
      onEnd?.()

      // Try next in queue
      if (queueRef.current.length > 0) {
        const next = queueRef.current.shift()
        playAudio(next.base64Audio, next.onEnd)
      }
    }

    audio.play().catch((err) => {
      console.error('Play failed:', err)
      setIsPlaying(false)
      audioRef.current = null
      onEnd?.()
    })
  }, [isPlaying])

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
      setIsPlaying(false)
      queueRef.current = []
    }
  }, [])

  return { playAudio, stopAudio, isPlaying }
}