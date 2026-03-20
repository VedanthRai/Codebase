import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { motion } from 'framer-motion'
import {
  Shield, ShieldAlert, ChevronDown, ChevronUp,
  Clock, Zap, FileCode, Copy, Check
} from 'lucide-react'
import MermaidDiagram from './MermaidDiagram'

const INTENT_COLORS = {
  explain: '#3b82f6',
  why: '#8b5cf6',
  flow: '#06b6d4',
  impact: '#f59e0b',
  debug: '#ef4444',
  architecture: '#10b981',
  health: '#84cc16',
  general: '#94a3b8',
}

const INTENT_LABELS = {
  explain: '📖 Explain',
  why: '🧠 Why',
  flow: '🔄 Flow',
  impact: '💥 Impact',
  debug: '🐛 Debug',
  architecture: '🏗 Architecture',
  health: '❤️ Health',
  general: '💬 General',
}

function CodeBlock({ language, children }) {
  const [copied, setCopied] = useState(false)
  const code = String(children)

  const copy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-lang">{language || 'code'}</span>
        <button onClick={copy} className="copy-btn">
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={vscDarkPlus}
        customStyle={{ margin: 0, borderRadius: '0 0 8px 8px', fontSize: '0.8rem' }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

function VerificationBadge({ verification }) {
  if (!verification) return null
  const score = verification.confidence_score
  const isGood = score >= 0.75 && verification.is_grounded

  return (
    <div className={`verification-badge ${isGood ? 'good' : 'warning'}`}>
      {isGood
        ? <Shield size={12} />
        : <ShieldAlert size={12} />
      }
      <span>{isGood ? 'Grounded' : 'Low Confidence'}</span>
      <span className="score">{Math.round(score * 100)}%</span>
    </div>
  )
}

function SourcesPanel({ chunks }) {
  const [open, setOpen] = useState(false)
  if (!chunks?.length) return null

  return (
    <div className="sources-panel">
      <button className="sources-toggle" onClick={() => setOpen(!open)}>
        <FileCode size={12} />
        <span>{chunks.length} source{chunks.length > 1 ? 's' : ''} retrieved</span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="sources-list"
        >
          {chunks.map((chunk, i) => (
            <div key={i} className="source-item">
              <span className="source-type">{chunk.chunk_type}</span>
              <span className="source-name">{chunk.name || 'block'}</span>
              <span className="source-file">{chunk.file_path}</span>
              <span className="source-lines">L{chunk.start_line}–{chunk.end_line}</span>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  )
}

export function UserMessage({ message }) {
  return (
    <motion.div
      className="message user-message"
      initial={{ opacity: 0, x: 20, y: 10 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
    >
      <div className="message-bubble user-bubble">
        {message.content}
      </div>
      <span className="message-time">
        {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
    </motion.div>
  )
}

export function AssistantMessage({ message }) {
  return (
    <motion.div
      className="message assistant-message"
      initial={{ opacity: 0, x: -20, y: 10 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
    >
      {/* Header badges */}
      <div className="message-meta">
        {message.intent && (
          <span
            className="intent-badge"
            style={{ backgroundColor: INTENT_COLORS[message.intent] + '22', color: INTENT_COLORS[message.intent] }}
          >
            {INTENT_LABELS[message.intent] || message.intent}
          </span>
        )}
        {message.processing_time && (
          <span className="time-badge">
            <Clock size={10} />
            {(message.processing_time / 1000).toFixed(1)}s
          </span>
        )}
        <VerificationBadge verification={message.verification} />
      </div>

      {/* Main content */}
      <div className="message-bubble assistant-bubble">
        <ReactMarkdown
          components={{
            code({ node, inline, className, children, ...props }) {
              const lang = /language-(\w+)/.exec(className || '')?.[1]
              if (inline) {
                return <code className="inline-code" {...props}>{children}</code>
              }
              return <CodeBlock language={lang}>{children}</CodeBlock>
            },
            table({ children }) {
              return <div className="table-wrapper"><table>{children}</table></div>
            },
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>

      {/* Diagrams */}
      {message.diagrams?.length > 0 && (
        <div className="message-diagrams">
          {message.diagrams.map((d, i) => (
            <MermaidDiagram
              key={i}
              code={d.mermaid_code}
              title={d.description}
              type={d.diagram_type}
            />
          ))}
        </div>
      )}

      {/* Sources */}
      <SourcesPanel chunks={message.chunks} />
    </motion.div>
  )
}

export function ThinkingMessage() {
  return (
    <motion.div
      className="message assistant-message"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      <div className="message-bubble assistant-bubble thinking">
        <div className="thinking-dots">
          <span>Agents working</span>
          <div className="dots">
            <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.2, delay: 0 }}>·</motion.span>
            <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.2, delay: 0.4 }}>·</motion.span>
            <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.2, delay: 0.8 }}>·</motion.span>
          </div>
        </div>
        <div className="agent-pills">
          {['Retrieval', 'Understanding', 'Verification'].map((a, i) => (
            <motion.span
              key={a}
              className="agent-pill"
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 2, delay: i * 0.6 }}
            >
              {a}
            </motion.span>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
