/**
 * 🔧 Quick Skill Chips — Floating Action Buttons
 * Glassmorphism pill buttons that send commands to backend
 */
import { motion } from 'framer-motion'

const SKILLS = [
  { id: 'weather', params: 'Pune', label: '🌤️ Weather', desc: 'Check Pune weather' },
  { id: 'timer', params: '60', label: '⏱️ Timer', desc: 'Set 60s timer' },
  { id: 'note', params: 'Remember this', label: '📝 Note', desc: 'Save a note' },
  { id: 'search', params: 'latest AI news', label: '🔍 Search', desc: 'Search the web' },
  { id: 'open_app', params: 'notepad', label: '📓 Notepad', desc: 'Open Notepad' },
  { id: 'screenshot', params: '', label: '📸 Capture', desc: 'Take screenshot' },
]

export default function SkillChips({ onSkillSelect, disabled = false, chatOpen = true }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5, duration: 0.4 }}
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        left: chatOpen ? '1.5rem' : '50%',
        transform: chatOpen ? 'none' : 'translateX(-50%)',
        transition: 'left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        display: 'flex',
        gap: '0.5rem',
        flexWrap: 'wrap',
        justifyContent: chatOpen ? 'flex-start' : 'center',
        maxWidth: '600px',
        zIndex: 20,
      }}
    >
      {SKILLS.map((skill, i) => (
        <motion.button
          key={skill.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 + i * 0.05 }}
          whileHover={{ scale: 1.05, y: -2 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => {
            if (!disabled) {
              const command = skill.params
                ? `[SKILL:${skill.id}:${skill.params}]`
                : `[SKILL:${skill.id}]`
              // Send as text message that triggers skill
              const text = skill.params 
                ? `${skill.desc}` 
                : skill.desc
              onSkillSelect?.(text)
            }
          }}
          disabled={disabled}
          title={skill.desc}
          style={{
            background: 'rgba(8, 16, 32, 0.7)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            border: '1px solid rgba(0, 212, 255, 0.15)',
            borderRadius: '20px',
            padding: '0.4rem 0.9rem',
            color: disabled ? 'var(--text-muted)' : '#00d4ff',
            fontSize: '0.78rem',
            fontFamily: "'Inter', sans-serif",
            fontWeight: 500,
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s ease',
            boxShadow: '0 2px 12px rgba(0, 0, 0, 0.2)',
            opacity: disabled ? 0.4 : 1,
          }}
          onMouseEnter={(e) => {
            if (!disabled) {
              e.target.style.borderColor = 'rgba(0, 212, 255, 0.4)'
              e.target.style.boxShadow = '0 4px 20px rgba(0, 212, 255, 0.15)'
            }
          }}
          onMouseLeave={(e) => {
            e.target.style.borderColor = 'rgba(0, 212, 255, 0.15)'
            e.target.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.2)'
          }}
        >
          {skill.label}
        </motion.button>
      ))}
    </motion.div>
  )
}