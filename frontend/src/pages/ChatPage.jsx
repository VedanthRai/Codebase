import React, { useState, useEffect, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Trash2, GitBranch, Zap, HelpCircle,
  Activity, Bug, Layout, Lightbulb
} from 'lucide-react'
import { useStore } from '../store'
import { UserMessage, AssistantMessage, ThinkingMessage } from '../components/ChatMessage'

const INTENT_SHORTCUTS = [
  { icon: HelpCircle, label: 'Explain', mode: 'explain', color: '#3b82f6' },
  { icon: Lightbulb, label: 'Why', mode: 'why', color: '#8b5cf6' },
  { icon: GitBranch, label: 'Flow', mode: 'flow', color: '#06b6d4' },
  { icon: Zap, label: 'Impact', mode: 'impact', color: '#f59e0b' },
  { icon: Bug, label: 'Debug', mode: 'debug', color: '#ef4444' },
  { icon: Layout, label: 'Arch', mode: 'architecture', color: '#10b981' },
]

const EXAMPLE_QUESTIONS = [
  "Why is the authentication module structured this way?",
  "What happens if I change the database connection handler?",
  "Trace the request flow from entry point to response",
  "What are the most critical dependencies in this codebase?",
  "Find potential performance bottlenecks",
  "Show me the architecture of the core module",
]

export default function ChatPage() {
  const { repoId } = useParams()
  const [searchParams] = useSearchParams()
  const { messages, isQuerying, query, clearMessages, currentRepo, loadRepo } = useStore()
  const [input, setInput] = useState('')
  const [activeMode, setActiveMode] = useState(null)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!currentRepo) loadRepo(repoId)
    // Handle pre-filled query from URL
    const preQuery = searchParams.get('q')
    if (preQuery) {
      setInput(preQuery)
      inputRef.current?.focus()
    }
  }, [repoId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isQuerying])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isQuerying) return
    setInput('')
    await query(repoId, text, activeMode)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleExample = (q) => {
    setInput(q)
    inputRef.current?.focus()
  }

  const handleSuggestedQuestion = (q) => {
    setInput(q)
    inputRef.current?.focus()
  }

  const isEmptyChat = messages.length === 0

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="chat-header">
        <div className="chat-title">
          <span>Chat</span>
          {currentRepo && (
            <span className="chat-repo-name">— {currentRepo.name}</span>
          )}
        </div>
        {messages.length > 0 && (
          <button className="clear-btn" onClick={clearMessages}>
            <Trash2 size={14} />
            Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="messages-container">
        <AnimatePresence>
          {isEmptyChat ? (
            <motion.div
              className="chat-empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="empty-icon">
                <Activity size={32} />
              </div>
              <h2>Ask anything about the codebase</h2>
              <p>The multi-agent system will retrieve, understand, and verify before answering.</p>

              <div className="example-grid">
                {EXAMPLE_QUESTIONS.map((q, i) => (
                  <motion.button
                    key={i}
                    className="example-btn"
                    onClick={() => handleExample(q)}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.05 * i }}
                    whileHover={{ scale: 1.02 }}
                  >
                    {q}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          ) : (
            <div className="messages-list">
              {messages.map(msg => (
                msg.role === 'user'
                  ? <UserMessage key={msg.id} message={msg} />
                  : msg.role === 'assistant'
                    ? <AssistantMessage key={msg.id} message={msg} onSuggestedQuestion={handleSuggestedQuestion} />
                    : (
                      <div key={msg.id} className="error-message">
                        {msg.content}
                      </div>
                    )
              ))}
              {isQuerying && <ThinkingMessage />}
              <div ref={messagesEndRef} />
            </div>
          )}
        </AnimatePresence>
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        {/* Mode selector */}
        <div className="mode-row">
          {INTENT_SHORTCUTS.map(({ icon: Icon, label, mode, color }) => (
            <button
              key={mode}
              className={`mode-pill ${activeMode === mode ? 'active' : ''}`}
              style={activeMode === mode ? { backgroundColor: color + '22', color, borderColor: color } : {}}
              onClick={() => setActiveMode(activeMode === mode ? null : mode)}
            >
              <Icon size={11} />
              {label}
            </button>
          ))}
          {activeMode && (
            <button className="mode-clear" onClick={() => setActiveMode(null)}>
              Auto
            </button>
          )}
        </div>

        {/* Text input */}
        <div className="input-row-chat">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeMode
              ? `Ask a ${activeMode} question...`
              : "Ask anything about the codebase..."
            }
            className="chat-textarea"
            rows={2}
            disabled={isQuerying}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || isQuerying}
          >
            <Send size={16} />
          </button>
        </div>
        <p className="input-hint">
          Enter to send · Shift+Enter for new line
          {activeMode && <span className="mode-hint"> · Mode: <strong>{activeMode}</strong></span>}
        </p>
      </div>
    </div>
  )
}
