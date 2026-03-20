import React, { useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  MessageSquare, GitBranch, Activity, FolderOpen,
  FileCode, Code2, Package, Zap, ArrowRight, Github
} from 'lucide-react'
import { useStore } from '../store'

const QUICK_ACTIONS = [
  { icon: MessageSquare, label: 'Ask a Question', desc: 'Chat with agents about the codebase', path: '/chat', color: '#7c3aed' },
  { icon: GitBranch, label: 'Architecture', desc: 'View auto-generated diagrams', path: '/architecture', color: '#0891b2' },
  { icon: Activity, label: 'Health Report', desc: 'Complexity & maintainability scores', path: '/health', color: '#10b981' },
  { icon: FolderOpen, label: 'File Explorer', desc: 'Browse and analyze files', path: '/explorer', color: '#f59e0b' },
]

const SUGGESTED_QUERIES = [
  "Why is this codebase structured this way?",
  "What are the entry points to this system?",
  "What happens if I change the main module?",
  "Explain the execution flow of the core logic",
  "What are the biggest code quality issues?",
  "Show me the dependency architecture",
]

export default function RepositoryPage() {
  const { repoId } = useParams()
  const { currentRepo, loadRepo } = useStore()

  useEffect(() => {
    if (!currentRepo || currentRepo.repo_id !== repoId) {
      loadRepo(repoId)
    }
  }, [repoId])

  if (!currentRepo) {
    return (
      <div className="page-loading">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="spinner"
        />
        <p>Loading repository...</p>
      </div>
    )
  }

  const langEntries = Object.entries(currentRepo.stats?.languages || {})
  const totalLangFiles = langEntries.reduce((a, [, v]) => a + v, 0)

  return (
    <div className="repo-page">
      {/* Header */}
      <motion.div
        className="repo-header"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="repo-title-row">
          <Github size={20} />
          <h1>{currentRepo.name}</h1>
        </div>
        <a href={currentRepo.url} target="_blank" rel="noreferrer" className="repo-url-link">
          {currentRepo.url}
        </a>
      </motion.div>

      {/* Stats grid */}
      <motion.div
        className="stats-grid"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        {[
          { label: 'Files', value: currentRepo.stats?.files, icon: FileCode },
          { label: 'Functions', value: currentRepo.stats?.functions, icon: Code2 },
          { label: 'Classes', value: currentRepo.stats?.classes, icon: Package },
          { label: 'Avg Complexity', value: currentRepo.stats?.avg_complexity?.toFixed(1), icon: Zap },
        ].map(({ label, value, icon: Icon }, i) => (
          <motion.div
            key={label}
            className="stat-card"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.05 * i + 0.2 }}
          >
            <Icon size={16} className="stat-icon" />
            <div className="stat-value">{value ?? '—'}</div>
            <div className="stat-label">{label}</div>
          </motion.div>
        ))}
      </motion.div>

      <div className="repo-body">
        {/* Left column */}
        <div className="repo-main">
          {/* Summary */}
          {currentRepo.summary && (
            <motion.div
              className="summary-card"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <h2>AI-Generated Summary</h2>
              <p>{currentRepo.summary}</p>
            </motion.div>
          )}

          {/* Quick actions */}
          <div className="quick-actions">
            <h2>Explore</h2>
            <div className="quick-actions-grid">
              {QUICK_ACTIONS.map(({ icon: Icon, label, desc, path, color }, i) => (
                <motion.div
                  key={path}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 * i + 0.4 }}
                >
                  <Link
                    to={`/repo/${repoId}${path}`}
                    className="quick-action-card"
                    style={{ '--accent': color }}
                  >
                    <div className="qa-icon" style={{ color, backgroundColor: color + '15' }}>
                      <Icon size={20} />
                    </div>
                    <div className="qa-text">
                      <span className="qa-label">{label}</span>
                      <span className="qa-desc">{desc}</span>
                    </div>
                    <ArrowRight size={14} className="qa-arrow" />
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Suggested queries */}
          <div className="suggested-queries">
            <h2>Suggested Questions</h2>
            <div className="query-chips">
              {SUGGESTED_QUERIES.map((q, i) => (
                <Link
                  key={i}
                  to={`/repo/${repoId}/chat?q=${encodeURIComponent(q)}`}
                  className="query-chip"
                >
                  {q}
                  <ArrowRight size={11} />
                </Link>
              ))}
            </div>
          </div>
        </div>

        {/* Right column */}
        <div className="repo-sidebar">
          {/* Languages */}
          <div className="info-card">
            <h3>Languages</h3>
            <div className="lang-list">
              {langEntries.map(([lang, count]) => (
                <div key={lang} className="lang-item">
                  <span className="lang-name">{lang}</span>
                  <div className="lang-bar-wrap">
                    <div
                      className="lang-bar"
                      style={{ width: `${(count / totalLangFiles) * 100}%` }}
                    />
                  </div>
                  <span className="lang-count">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Critical modules */}
          {currentRepo.critical_modules?.length > 0 && (
            <div className="info-card">
              <h3>Critical Modules</h3>
              <div className="module-list">
                {currentRepo.critical_modules.slice(0, 8).map((m, i) => (
                  <div key={i} className="module-item">
                    <span className="module-rank">#{i + 1}</span>
                    <span className="module-name">{m.split('/').pop()}</span>
                    <span className="module-path">{m}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Entry points */}
          {currentRepo.entry_points?.length > 0 && (
            <div className="info-card">
              <h3>Entry Points</h3>
              <div className="entry-list">
                {currentRepo.entry_points.slice(0, 6).map((e, i) => (
                  <div key={i} className="entry-item">
                    <Code2 size={12} />
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
