/**
 * 💬 Chat Panel — Glassmorphism Conversation Display
 * With text input, animated messages, typing indicator, auto-scroll, and IMAGE UPLOAD
 */
import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export default function ChatPanel({
  messages = [],
  isProcessing = false,
  onSendText,
  onSendImage, // NAYA PROP: Image bhejne ke liye
  onClear,
  isVisible = true,
}) {
  const [inputText, setInputText] = useState('')
  const [selectedImage, setSelectedImage] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  
  const scrollRef = useRef(null)
  const fileInputRef = useRef(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [messages, isProcessing])

  // Handle file selection
  const handleFileChange = (e) => {
    const file = e.target.files[0]
    if (file && file.type.startsWith('image/')) {
      setSelectedImage(file)
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  // Remove selected image
  const removeImage = () => {
    setSelectedImage(null)
    setPreviewUrl(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const text = inputText.trim()
    if (isProcessing) return

    if (selectedImage) {
      // Send Image along with prompt text
      onSendImage?.(selectedImage, text)
      removeImage()
      setInputText('')
    } else if (text) {
      // Send regular Text
      onSendText?.(text)
      setInputText('')
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  if (!isVisible) return null

  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: 'fixed',
        right: '1.5rem',
        top: '5rem',
        bottom: '1.5rem',
        width: '380px',
        maxWidth: 'calc(100vw - 3rem)',
        background: 'rgba(8, 16, 32, 0.75)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        border: '1px solid rgba(0, 212, 255, 0.12)',
        borderRadius: '20px',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 8px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05)',
        zIndex: 20,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid rgba(0, 212, 255, 0.1)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div
          style={{
            fontFamily: "'Orbitron', monospace",
            fontSize: '0.8rem',
            fontWeight: 600,
            letterSpacing: '2px',
            color: '#00d4ff',
            textShadow: '0 0 10px rgba(0, 212, 255, 0.3)',
          }}
        >
          💬 CONVERSATION
        </div>
        <button
          onClick={onClear}
          title="Clear conversation"
          style={{
            background: 'rgba(255, 58, 58, 0.1)',
            border: '1px solid rgba(255, 58, 58, 0.2)',
            borderRadius: '8px',
            color: '#ff3a3a',
            fontSize: '0.75rem',
            padding: '0.3rem 0.6rem',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            fontFamily: "'Share Tech Mono', monospace",
          }}
        >
          🗑️ CLEAR
        </button>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '1rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
      >
        <AnimatePresence>
          {messages.length === 0 && !isProcessing && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={{
                textAlign: 'center',
                color: 'var(--text-dim)',
                marginTop: '4rem',
                fontFamily: "'Share Tech Mono', monospace",
                fontSize: '0.85rem',
              }}
            >
              <div style={{ fontSize: '2.5rem', marginBottom: '1rem', opacity: 0.5 }}>
                🎙️
              </div>
              <p>Hold the mic button, type, or upload an image below</p>
            </motion.div>
          )}

          {messages.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{
                opacity: 0,
                x: msg.role === 'user' ? -15 : 15,
                y: 5,
              }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              style={{
                padding: '0.8rem 1rem',
                background:
                  msg.role === 'user'
                    ? 'rgba(0, 212, 255, 0.08)'
                    : 'rgba(0, 255, 136, 0.06)',
                borderRadius: '12px',
                borderLeft:
                  msg.role === 'user'
                    ? '3px solid rgba(0, 212, 255, 0.5)'
                    : '3px solid rgba(0, 255, 136, 0.5)',
              }}
            >
              <div
                style={{
                  fontSize: '0.65rem',
                  fontFamily: "'Orbitron', monospace",
                  fontWeight: 600,
                  letterSpacing: '1.5px',
                  color: msg.role === 'user' ? '#00d4ff' : '#00ff88',
                  marginBottom: '0.3rem',
                }}
              >
                {msg.role === 'user' ? 'YOU' : 'MAX'}
              </div>
              <div
                style={{
                  fontSize: '0.88rem',
                  lineHeight: 1.5,
                  color: 'var(--text-primary)',
                  fontFamily: "'Inter', sans-serif",
                }}
              >
                {msg.content}
              </div>
            </motion.div>
          ))}

          {/* Typing indicator */}
          {isProcessing && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{
                padding: '0.8rem 1rem',
                background: 'rgba(255, 215, 0, 0.05)',
                borderRadius: '12px',
                borderLeft: '3px solid rgba(255, 215, 0, 0.4)',
              }}
            >
              <div
                style={{
                  fontSize: '0.65rem',
                  fontFamily: "'Orbitron', monospace",
                  fontWeight: 600,
                  letterSpacing: '1.5px',
                  color: '#ffd700',
                  marginBottom: '0.3rem',
                }}
              >
                MAX
              </div>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: '#ffd700',
                      animation: `ambientPulse 1s ease infinite ${i * 0.15}s`,
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input Area (Preview + Text Input) */}
      <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid rgba(0, 212, 255, 0.1)' }}>
        
        {/* Image Preview Block */}
        {previewUrl && (
          <div style={{ 
            position: 'relative', 
            marginBottom: '10px', 
            display: 'inline-block' 
          }}>
            <img 
              src={previewUrl} 
              alt="Preview" 
              style={{ 
                height: '60px', 
                borderRadius: '8px', 
                border: '1px solid rgba(0, 212, 255, 0.4)' 
              }} 
            />
            <button
              onClick={removeImage}
              style={{
                position: 'absolute',
                top: '-5px',
                right: '-5px',
                background: '#ff3a3a',
                color: 'white',
                border: 'none',
                borderRadius: '50%',
                width: '20px',
                height: '20px',
                cursor: 'pointer',
                fontSize: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              ✕
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
          {/* Hidden File Input */}
          <input
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            ref={fileInputRef}
            onChange={handleFileChange}
          />
          
          {/* Attachment Button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessing}
            style={{
              background: 'rgba(0, 212, 255, 0.05)',
              border: '1px solid rgba(0, 212, 255, 0.15)',
              borderRadius: '10px',
              padding: '0 0.8rem',
              color: '#00d4ff',
              cursor: isProcessing ? 'default' : 'pointer',
              transition: 'all 0.2s',
            }}
          >
            📎
          </button>

          {/* Text Input */}
          <input
            id="chat-input"
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message or image prompt..."
            disabled={isProcessing}
            style={{
              flex: 1,
              background: 'rgba(0, 212, 255, 0.05)',
              border: '1px solid rgba(0, 212, 255, 0.15)',
              borderRadius: '10px',
              padding: '0.6rem 1rem',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
              outline: 'none',
            }}
          />
          
          {/* Send Button */}
          <button
            type="submit"
            disabled={isProcessing || (!inputText.trim() && !selectedImage)}
            style={{
              background: (inputText.trim() || selectedImage)
                ? 'linear-gradient(135deg, #00d4ff, #00a0cc)'
                : 'rgba(0, 212, 255, 0.1)',
              border: 'none',
              borderRadius: '10px',
              padding: '0.6rem 1rem',
              color: (inputText.trim() || selectedImage) ? '#050a0f' : 'var(--text-dim)',
              fontWeight: 600,
              cursor: (inputText.trim() || selectedImage) ? 'pointer' : 'default',
            }}
          >
            ↗
          </button>
        </form>
      </div>
    </motion.div>
  )
}