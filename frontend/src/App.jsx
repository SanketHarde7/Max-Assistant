/**
 * 🤖 MAX v2.0 — Immersive 3D AI Assistant
 * Full integration: 3D Orb + Voice Pipeline + Text Chat + Skills
 * Built with Three.js, Framer Motion & Glassmorphism
 */
import { useState, useCallback, Suspense, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { motion, AnimatePresence } from 'framer-motion'

// Components
import BootSequence from './components/BootSequence.jsx'
import OrbCore from './components/OrbCore.jsx'
import WaveVisualizer from './components/WaveVisualizer.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import StatusBar from './components/StatusBar.jsx'
import SkillChips from './components/SkillChips.jsx'

// Hooks
import { useWebSocket } from './hooks/useWebSocket.js'
import { useVoiceInput } from './hooks/useVoiceInput.js'
import { useAudioPlayer } from './hooks/useAudioPlayer.js'

// ── Helpers ──
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    if (!blob || !(blob instanceof Blob)) {
      reject(new Error('Invalid audio blob'))
      return
    }
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result.split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function App() {
  // ── State ──
  const [booting, setBooting] = useState(true)
  const [jarvisState, setMaxState] = useState('idle')
  const [messages, setMessages] = useState([])
  const [error, setError] = useState(null)
  const [chatOpen, setChatOpen] = useState(true)

  // ── Hooks ──
  const { playAudio, stopAudio, isPlaying } = useAudioPlayer()
  const { startRecording, stopRecording, isRecording, analyserNode } = useVoiceInput()

  // ── WebSocket Event Handler ──
  const handleWsEvent = useCallback(
    (data) => {
      const event = data?.event || data?.type

      switch (event) {
        case 'greeting':
          if (data.text) {
            setMessages((prev) => [
              ...prev,
              { role: 'jarvis', content: data.text },
            ])
          }
          setMaxState('idle')
          break

        case 'status_update':
          if (data.state) setMaxState(data.state)
          break

        case 'transcript':
          if (data.text) {
            setMessages((prev) => [
              ...prev,
              { role: 'user', content: data.text },
            ])
          }
          break

        case 'response_text':
          if (data.text) {
            setMessages((prev) => [
              ...prev,
              { role: 'jarvis', content: data.text },
            ])
          }
          setMaxState('idle')
          break

        case 'response':
          if (data.text) {
            setMessages((prev) => [
              ...prev,
              { role: 'jarvis', content: data.text },
            ])
          }
          setMaxState('idle')
          break

        case 'audio_response':
          if (data.audio) {
            setMaxState('speaking')
            playAudio(data.audio, () => {
              setMaxState('idle')
            })
          } else {
            setMaxState('idle')
          }
          break

        case 'skill_event':
          console.log('Skill executed:', data.skill)
          break

        case 'error':
          setError(data.message || 'Unknown error')
          setMaxState('idle')
          setTimeout(() => setError(null), 5000)
          break

        case 'pong':
          break

        default:
          console.log('Unknown WS event:', data)
      }
    },
    [playAudio]
  )

  const { isConnected, sendVoice, sendText } = useWebSocket(
    'ws://localhost:8000/ws',
    { onEvent: handleWsEvent }
  )

  // ── Global Kill Switch ──
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        console.log('🛑 Kill switch triggered')
        stopAudio()
        setMaxState('idle')

        try {
          const ws = new WebSocket('ws://localhost:8000/ws')
          ws.onopen = () => {
            ws.send(JSON.stringify({ type: 'abort' }))
            ws.close()
          }
        } catch (err) {
          console.warn('Could not send abort signal', err)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [stopAudio])

  // ── Voice Handlers ──
  const handleMicPress = async () => {
    if (isRecording || jarvisState === 'thinking' || jarvisState === 'speaking')
      return
    try {
      setError(null)
      await startRecording()
      setMaxState('listening')
    } catch (err) {
      setError('Microphone access denied. Please allow mic permissions.')
      setMaxState('idle')
    }
  }

  const handleMicRelease = async () => {
    if (!isRecording) return
    setMaxState('thinking')

    try {
      const audioBlob = await stopRecording()
      if (!audioBlob || audioBlob.size < 512) {
        setError('Audio too short. Hold button longer.')
        setMaxState('idle')
        return
      }

      const base64 = await blobToBase64(audioBlob)

      // Try WebSocket first, fallback to REST
      if (isConnected) {
        sendVoice(base64)
      } else {
        // REST fallback
        const response = await fetch('http://localhost:8000/api/voice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audio: base64 }),
        })

        if (!response.ok) {
          const err = await response.json()
          throw new Error(err.detail || 'Processing failed')
        }

        const result = await response.json()

        setMessages((prev) => [
          ...prev,
          { role: 'user', content: result.transcript },
          { role: 'jarvis', content: result.response },
        ])

        if (result.audio) {
          setMaxState('speaking')
          playAudio(result.audio, () => setMaxState('idle'))
        } else {
          setMaxState('idle')
        }
      }
    } catch (err) {
      console.error('Voice error:', err)
      setError(err.message)
      setMaxState('idle')
    }
  }

  // ── Text Chat Handler ──
  const handleSendText = async (text) => {
    if (!text.trim() || jarvisState === 'thinking' || jarvisState === 'speaking')
      return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setMaxState('thinking')
    setError(null)

    // Try WebSocket first
    if (isConnected) {
      sendText(text)
    } else {
      // REST fallback
      try {
        const response = await fetch('http://localhost:8000/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session_id: 'default' }),
        })

        if (!response.ok) {
          const err = await response.json()
          throw new Error(err.detail || 'Chat failed')
        }

        const result = await response.json()

        setMessages((prev) => [
          ...prev,
          { role: 'jarvis', content: result.response },
        ])

        if (result.audio) {
          setMaxState('speaking')
          playAudio(result.audio, () => setMaxState('idle'))
        } else {
          setMaxState('idle')
        }
      } catch (err) {
        console.error('Chat error:', err)
        setError(err.message)
        setMaxState('idle')
      }
    }
  }

  // ── Clear Chat ──
  const handleClearChat = async () => {
    setMessages([])
    try {
      await fetch('http://localhost:8000/api/memory', { method: 'DELETE' })
    } catch (e) {
      console.warn('Memory clear failed:', e)
    }
  }

  // ── Skill Chip Handler ──
  const handleSkillSelect = (text) => {
    handleSendText(text)
  }

  // ── Boot Screen ──
  if (booting) {
    return <BootSequence onComplete={() => setBooting(false)} />
  }

  // ── Mic Button Colors ──
  const micColors = {
    idle: {
      bg: 'linear-gradient(135deg, #00d4ff 0%, #0099cc 100%)',
      shadow: '0 0 30px rgba(0, 212, 255, 0.35)',
      text: '#050a0f',
    },
    listening: {
      bg: 'linear-gradient(135deg, #00ff88 0%, #00cc6a 100%)',
      shadow: '0 0 40px rgba(0, 255, 136, 0.5)',
      text: '#050a0f',
    },
    thinking: {
      bg: 'linear-gradient(135deg, #ffd700 0%, #cc9900 100%)',
      shadow: '0 0 30px rgba(255, 215, 0, 0.3)',
      text: '#050a0f',
    },
    speaking: {
      bg: 'rgba(255, 58, 138, 0.2)',
      shadow: '0 0 20px rgba(255, 58, 138, 0.2)',
      text: '#ff3a8a',
    },
  }
  const micStyle = micColors[jarvisState] || micColors.idle

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background:
          'linear-gradient(135deg, #020408 0%, #050a0f 30%, #0a1628 70%, #050a0f 100%)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Ambient background glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 50% 45%, rgba(0, 212, 255, 0.06) 0%, transparent 60%)`,
          pointerEvents: 'none',
          animation: 'ambientPulse 8s ease-in-out infinite',
        }}
      />

      {/* Grid overlay */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(0, 212, 255, 0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 212, 255, 0.02) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
          pointerEvents: 'none',
          opacity: 0.5,
        }}
      />

      {/* Status Bar */}
      <StatusBar
        state={jarvisState}
        connected={isConnected}
        error={error}
        onToggleChat={() => setChatOpen(!chatOpen)}
        chatOpen={chatOpen}
      />

      {/* 3D Scene — Full Screen Canvas */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 1,
        }}
      >
        <Canvas
          camera={{ position: [0, 0, 8], fov: 45 }}
          gl={{ antialias: true, alpha: true }}
          style={{ background: 'transparent' }}
        >
          <Suspense fallback={null}>
            <OrbCore state={jarvisState} />
          </Suspense>
          <OrbitControls
            enableZoom={false}
            enablePan={false}
            autoRotate
            autoRotateSpeed={0.3}
            maxPolarAngle={Math.PI / 1.5}
            minPolarAngle={Math.PI / 3}
          />
        </Canvas>
      </div>

      {/* Circular Waveform Overlay */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: chatOpen ? 'calc(50% - 190px)' : '50%',
          transform: 'translate(-50%, -50%)',
          width: '500px',
          height: '500px',
          zIndex: 2,
          pointerEvents: 'none',
          transition: 'left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <WaveVisualizer
          isActive={isRecording || isPlaying}
          mode={jarvisState}
          analyserNode={analyserNode}
        />
      </div>

      {/* Center Status Text + Mic Button */}
      <div
        style={{
          position: 'absolute',
          bottom: '6rem',
          left: chatOpen ? 'calc(50% - 190px)' : '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '1.5rem',
          zIndex: 10,
          transition: 'left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* State Label */}
        <AnimatePresence mode="wait">
          <motion.div
            key={jarvisState}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            style={{
              fontFamily: "'Orbitron', monospace",
              fontSize: '0.85rem',
              fontWeight: 600,
              letterSpacing: '4px',
              color:
                jarvisState === 'idle'
                  ? '#00d4ff'
                  : jarvisState === 'listening'
                  ? '#00ff88'
                  : jarvisState === 'thinking'
                  ? '#ffd700'
                  : '#ff3a8a',
              textShadow: `0 0 20px currentColor`,
            }}
          >
            {jarvisState === 'idle' && '◆ SYSTEM READY'}
            {jarvisState === 'listening' && '● LISTENING...'}
            {jarvisState === 'thinking' && '◇ PROCESSING...'}
            {jarvisState === 'speaking' && '♪ RESPONDING...'}
          </motion.div>
        </AnimatePresence>

        {/* Main Mic Button */}
        <motion.button
          id="mic-button"
          onMouseDown={handleMicPress}
          onMouseUp={handleMicRelease}
          onTouchStart={(e) => {
            e.preventDefault()
            handleMicPress()
          }}
          onTouchEnd={(e) => {
            e.preventDefault()
            handleMicRelease()
          }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.92 }}
          disabled={jarvisState === 'thinking' || jarvisState === 'speaking'}
          style={{
            padding: '1rem 2.8rem',
            fontSize: '0.9rem',
            fontWeight: 700,
            fontFamily: "'Orbitron', monospace",
            letterSpacing: '3px',
            background: micStyle.bg,
            color: micStyle.text,
            border: 'none',
            borderRadius: '50px',
            cursor:
              jarvisState === 'thinking' || jarvisState === 'speaking'
                ? 'not-allowed'
                : 'pointer',
            boxShadow: micStyle.shadow,
            transition: 'all 0.3s ease',
            opacity:
              jarvisState === 'thinking' || jarvisState === 'speaking'
                ? 0.5
                : 1,
            userSelect: 'none',
            WebkitUserSelect: 'none',
          }}
        >
          {isRecording
            ? '🔴  RELEASE TO SEND'
            : jarvisState === 'thinking'
            ? '⏳  PROCESSING...'
            : jarvisState === 'speaking'
            ? '🔊  SPEAKING...'
            : '🎙️  HOLD TO SPEAK'}
        </motion.button>

        {/* NEW: Explicit Kill Switch Button */}
        <AnimatePresence>
          {(jarvisState === 'thinking' || jarvisState === 'speaking') && (
            <motion.button
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              onClick={() => {
                console.log('🛑 Kill switch triggered via UI');
                stopAudio();
                setMaxState('idle');
                try {
                  const ws = new WebSocket('ws://localhost:8000/ws');
                  ws.onopen = () => {
                    ws.send(JSON.stringify({ type: 'abort' }));
                    ws.close();
                  };
                } catch (err) {
                  console.warn('Could not send abort signal', err);
                }
              }}
              style={{
                marginTop: '10px',
                padding: '0.6rem 1.5rem',
                fontSize: '0.8rem',
                fontWeight: 600,
                fontFamily: "'Orbitron', monospace",
                background: 'rgba(255, 58, 58, 0.1)',
                color: '#ff3a3a',
                border: '1px solid rgba(255, 58, 58, 0.5)',
                borderRadius: '8px',
                cursor: 'pointer',
                boxShadow: '0 0 10px rgba(255, 58, 58, 0.2)',
                transition: 'all 0.2s',
              }}
              whileHover={{ background: 'rgba(255, 58, 58, 0.2)', scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              🛑 STOP MAX
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* Chat Panel */}
      <AnimatePresence>
        {chatOpen && (
          <ChatPanel
            messages={messages}
            isProcessing={jarvisState === 'thinking'}
            onSendText={handleSendText}
            onClear={handleClearChat}
            isVisible={chatOpen}
          />
        )}
      </AnimatePresence>

      {/* Skill Chips */}
      <SkillChips
        onSkillSelect={handleSkillSelect}
        disabled={jarvisState === 'thinking' || jarvisState === 'speaking'}
        chatOpen={chatOpen}
      />
    </div>
  )
}

export default App