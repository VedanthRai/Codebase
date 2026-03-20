import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Activity, Zap, Link2, Code2, TestTube,
  AlertTriangle, CheckCircle, Info, RefreshCw
} from 'lucide-react'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import axios from 'axios'
import { useStore } from '../store'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SEVERITY_CONFIG = {
  CRITICAL: { color: '#ef4444', icon: AlertTriangle },
  HIGH: { color: '#f97316', icon: AlertTriangle },
  MEDIUM: { color: '#f59e0b', icon: Info },
  LOW: { color: '#10b981', icon: CheckCircle },
}

function ScoreRing({ score, label, color, icon: Icon }) {
  const circumference = 2 * Math.PI * 42
  const offset = circumference - (score / 100) * circumference

  return (
    <div className="score-ring-wrap">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--surface-2)" strokeWidth="8" />
        <motion.circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1, ease: 'easeOut', delay: 0.3 }}
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="50" textAnchor="middle" dominantBaseline="central"
          fill={color} fontSize="18" fontWeight="700">
          {Math.round(score)}
        </text>
      </svg>
      <div className="score-ring-label">
        <Icon size={12} style={{ color }} />
        <span>{label}</span>
      </div>
    </div>
  )
}

export default function HealthPage() {
  const { repoId } = useParams()
  const { currentRepo, loadRepo } = useStore()
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentRepo) loadRepo(repoId)
    fetchHealth()
  }, [repoId])

  const fetchHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(`${API}/api/repos/${repoId}/health`)
      setHealth(data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  const overallColor = health
    ? health.overall_score > 70 ? '#10b981' : health.overall_score > 50 ? '#f59e0b' : '#ef4444'
    : '#94a3b8'

  const radarData = health ? [
    { metric: 'Complexity', score: health.complexity_score },
    { metric: 'Coupling', score: health.coupling_score },
    { metric: 'Maintainability', score: health.maintainability_score },
    { metric: 'Test Coverage', score: health.test_coverage_score },
  ] : []

  const barData = health ? [
    { name: 'Complexity', score: health.complexity_score, color: '#7c3aed' },
    { name: 'Coupling', score: health.coupling_score, color: '#0891b2' },
    { name: 'Maintainability', score: health.maintainability_score, color: '#10b981' },
    { name: 'Test Coverage', score: health.test_coverage_score, color: '#f59e0b' },
  ] : []

  return (
    <div className="health-page">
      <div className="page-header">
        <div>
          <h1>Repository Health</h1>
          <p className="page-subtitle">Code quality metrics and recommendations</p>
        </div>
        <button className="refresh-btn" onClick={fetchHealth} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </div>

      {loading && (
        <div className="page-loading">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            className="spinner"
          />
          <p>Computing health metrics...</p>
        </div>
      )}

      {error && <div className="error-banner"><p>{error}</p></div>}

      {health && !loading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
        >
          {/* Overall score hero */}
          <div className="health-hero">
            <div className="overall-score" style={{ '--score-color': overallColor }}>
              <div className="overall-ring">
                <svg width="160" height="160" viewBox="0 0 160 160">
                  <circle cx="80" cy="80" r="68" fill="none"
                    stroke="var(--surface-2)" strokeWidth="12" />
                  <motion.circle
                    cx="80" cy="80" r="68"
                    fill="none" stroke={overallColor} strokeWidth="12"
                    strokeLinecap="round"
                    strokeDasharray={2 * Math.PI * 68}
                    strokeDashoffset={2 * Math.PI * 68}
                    animate={{ strokeDashoffset: 2 * Math.PI * 68 * (1 - health.overall_score / 100) }}
                    transition={{ duration: 1.2, ease: 'easeOut' }}
                    transform="rotate(-90 80 80)"
                  />
                  <text x="80" y="72" textAnchor="middle" fill={overallColor} fontSize="32" fontWeight="800">
                    {Math.round(health.overall_score)}
                  </text>
                  <text x="80" y="94" textAnchor="middle" fill="var(--text-muted)" fontSize="12">
                    / 100
                  </text>
                </svg>
              </div>
              <div className="overall-label">
                <Activity size={18} style={{ color: overallColor }} />
                <span>Overall Health</span>
              </div>
            </div>

            <div className="score-rings">
              <ScoreRing score={health.complexity_score} label="Complexity" color="#7c3aed" icon={Zap} />
              <ScoreRing score={health.coupling_score} label="Coupling" color="#0891b2" icon={Link2} />
              <ScoreRing score={health.maintainability_score} label="Maintainability" color="#10b981" icon={Code2} />
              <ScoreRing score={health.test_coverage_score} label="Test Coverage" color="#f59e0b" icon={TestTube} />
            </div>
          </div>

          {/* Charts */}
          <div className="health-charts">
            <div className="chart-card">
              <h3>Score Breakdown</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={barData} barSize={32}>
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--surface-1)', border: '1px solid var(--border)' }}
                    labelStyle={{ color: 'var(--text)' }}
                  />
                  <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                    {barData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-card">
              <h3>Radar Overview</h3>
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <Radar
                    name="Score" dataKey="score"
                    stroke="#7c3aed" fill="#7c3aed" fillOpacity={0.25}
                    strokeWidth={2}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Issues */}
          {health.issues?.length > 0 && (
            <div className="health-issues">
              <h2>Issues Found</h2>
              <div className="issues-list">
                {health.issues.map((issue, i) => {
                  const { color, icon: Icon } = SEVERITY_CONFIG[issue.severity] || SEVERITY_CONFIG.LOW
                  return (
                    <motion.div
                      key={i}
                      className="issue-card"
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.05 * i }}
                      style={{ borderLeftColor: color }}
                    >
                      <Icon size={14} style={{ color }} />
                      <div className="issue-text">
                        <span className="issue-type">{issue.type}</span>
                        <span className="issue-message">{issue.message}</span>
                      </div>
                      <span className="severity-tag" style={{ color, borderColor: color }}>
                        {issue.severity}
                      </span>
                    </motion.div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {health.recommendations?.length > 0 && (
            <div className="health-recommendations">
              <h2>Recommendations</h2>
              <div className="rec-list">
                {health.recommendations.map((rec, i) => (
                  <motion.div
                    key={i}
                    className="rec-card"
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.05 * i + 0.2 }}
                  >
                    <CheckCircle size={14} className="rec-icon" />
                    <span>{rec}</span>
                  </motion.div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}
