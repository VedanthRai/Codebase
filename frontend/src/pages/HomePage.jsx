import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Github, Cpu, Zap, Shield, GitBranch, ArrowRight, AlertCircle } from 'lucide-react'
import { useStore } from '../store'

const DEMO_REPOS = [
  { url: 'https://github.com/pallets/flask', label: 'Flask', desc: 'Python web framework' },
  { url: 'https://github.com/fastapi/fastapi', label: 'FastAPI', desc: 'Modern Python API framework' },
  { url: 'https://github.com/expressjs/express', label: 'Express.js', desc: 'Node.js web framework' },
]

const FEATURE_CARDS = [
  { icon: Cpu, title: 'Multi-Agent RAG', desc: '7 specialized agents for deep code understanding', color: '#7c3aed' },
  { icon: GitBranch, title: 'Dependency Graphs', desc: 'Visual maps of how your code connects', color: '#0891b2' },
  { icon: Zap, title: '"Why" Mode', desc: 'Explains design decisions, not just behavior', color: '#f59e0b' },
  { icon: Shield, title: 'Hallucination Guard', desc: 'Every response verified against source code', color: '#10b981' },
]

export default function HomePage() {
  const navigate = useNavigate()
  const { ingestRepo, isIngesting, ingestProgress, ingestMessage, ingestError, repos, loadRepos } = useStore()
  const [url, setUrl] = useState('')
  const [branch, setBranch] = useState('main')

  useEffect(() => { loadRepos() }, [])

  const handleIngest = async (repoUrl = url) => {
    if (!repoUrl.trim()) return
    try {
      const repoId = await ingestRepo(repoUrl.trim(), branch)
      navigate(`/repo/${repoId}`)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="home-page">
      {/* Hero */}
      <div className="hero">
        <motion.div
          className="hero-content"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="hero-badge">
            <Cpu size={14} />
            <span>Multi-Agent RAG System</span>
          </div>

          <h1 className="hero-title">
            <span className="gradient-text">CodeOracle</span>
          </h1>
          <p className="hero-subtitle">
            Don't just read code. <em>Understand it.</em>
            <br />
            Deep explainability for any GitHub repository.
          </p>

          {/* Input form */}
          <div className="ingest-form">
            <div className="input-row">
              <div className="input-wrapper">
                <Github size={16} className="input-icon" />
                <input
                  type="text"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleIngest()}
                  placeholder="https://github.com/owner/repository"
                  className="repo-input"
                  disabled={isIngesting}
                />
              </div>
              <input
                type="text"
                value={branch}
                onChange={e => setBranch(e.target.value)}
                placeholder="main"
                className="branch-input"
                disabled={isIngesting}
              />
              <button
                className="ingest-btn"
                onClick={() => handleIngest()}
                disabled={isIngesting || !url.trim()}
              >
                {isIngesting ? 'Analyzing...' : 'Analyze'}
                <ArrowRight size={16} />
              </button>
            </div>

            {/* Demo repos */}
            <div className="demo-repos">
              <span className="demo-label">Try:</span>
              {DEMO_REPOS.map(r => (
                <button key={r.url} className="demo-chip" onClick={() => {
                  setUrl(r.url)
                  handleIngest(r.url)
                }}>
                  {r.label}
                </button>
              ))}
            </div>

            {/* Progress */}
            <AnimatePresence>
              {isIngesting && (
                <motion.div
                  className="progress-container"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <div className="progress-text">
                    <span>{ingestMessage}</span>
                    <span>{ingestProgress}%</span>
                  </div>
                  <div className="progress-bar">
                    <motion.div
                      className="progress-fill"
                      animate={{ width: `${ingestProgress}%` }}
                      transition={{ duration: 0.4 }}
                    />
                  </div>
                </motion.div>
              )}
              {ingestError && (
                <motion.div
                  className="error-banner"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <AlertCircle size={14} />
                  <span>{ingestError}</span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Feature cards */}
          <div className="feature-grid">
            {FEATURE_CARDS.map(({ icon: Icon, title, desc, color }, i) => (
              <motion.div
                key={title}
                className="feature-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * i + 0.3 }}
                style={{ '--accent': color }}
              >
                <div className="feature-icon" style={{ color }}>
                  <Icon size={20} />
                </div>
                <h3>{title}</h3>
                <p>{desc}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Existing repos */}
      {repos.length > 0 && (
        <div className="existing-repos">
          <h2>Recent Repositories</h2>
          <div className="repo-list">
            {repos.map(repo => (
              <motion.div
                key={repo.repo_id}
                className="repo-card"
                whileHover={{ scale: 1.02 }}
                onClick={() => navigate(`/repo/${repo.repo_id}`)}
              >
                <div className="repo-card-header">
                  <Github size={16} />
                  <span className="repo-name">{repo.name}</span>
                </div>
                <div className="repo-stats">
                  <span>{repo.files} files</span>
                  <span>·</span>
                  <span>{repo.functions} functions</span>
                  <span>·</span>
                  <span>{Object.keys(repo.languages).join(', ')}</span>
                </div>
                <ArrowRight size={14} className="repo-arrow" />
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
