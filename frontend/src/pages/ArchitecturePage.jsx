import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RefreshCw, GitBranch, Layers, Share2, ArrowRightLeft } from 'lucide-react'
import axios from 'axios'
import { useStore } from '../store'
import MermaidDiagram from '../components/MermaidDiagram'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const DIAGRAM_ICONS = {
  architecture: Layers,
  dependency: Share2,
  call_graph: ArrowRightLeft,
  sequence: GitBranch,
  class: GitBranch,
}

export default function ArchitecturePage() {
  const { repoId } = useParams()
  const { currentRepo, loadRepo } = useStore()
  const [diagrams, setDiagrams] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState(0)

  useEffect(() => {
    if (!currentRepo) loadRepo(repoId)
    fetchDiagrams()
  }, [repoId])

  const fetchDiagrams = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(`${API}/api/repos/${repoId}/architecture`)
      setDiagrams(data.diagrams || [])
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="arch-page">
      <div className="page-header">
        <div>
          <h1>Architecture</h1>
          <p className="page-subtitle">Auto-generated diagrams from static analysis</p>
        </div>
        <button className="refresh-btn" onClick={fetchDiagrams} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          Regenerate
        </button>
      </div>

      {loading && (
        <div className="page-loading">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            className="spinner"
          />
          <p>Generating diagrams from codebase analysis...</p>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <p>{error}</p>
        </div>
      )}

      {!loading && diagrams.length > 0 && (
        <>
          {/* Tab bar */}
          <div className="diagram-tabs">
            {diagrams.map((d, i) => {
              const Icon = DIAGRAM_ICONS[d.diagram_type] || GitBranch
              return (
                <button
                  key={i}
                  className={`diagram-tab ${activeTab === i ? 'active' : ''}`}
                  onClick={() => setActiveTab(i)}
                >
                  <Icon size={14} />
                  {d.diagram_type.replace('_', ' ')}
                </button>
              )
            })}
          </div>

          {/* Active diagram */}
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <MermaidDiagram
              code={diagrams[activeTab].mermaid_code}
              title={diagrams[activeTab].description}
              type={diagrams[activeTab].diagram_type}
            />

            {/* Involved components */}
            {diagrams[activeTab].involved_components?.length > 0 && (
              <div className="components-panel">
                <h3>Involved Components</h3>
                <div className="component-chips">
                  {diagrams[activeTab].involved_components.map((c, i) => (
                    <span key={i} className="component-chip">{c.split('/').pop()}</span>
                  ))}
                </div>
              </div>
            )}
          </motion.div>

          {/* All diagrams overview */}
          {diagrams.length > 1 && (
            <div className="all-diagrams">
              <h2>All Diagrams</h2>
              <div className="diagrams-grid">
                {diagrams.map((d, i) => (
                  <motion.div
                    key={i}
                    className={`diagram-thumb ${activeTab === i ? 'active-thumb' : ''}`}
                    onClick={() => setActiveTab(i)}
                    whileHover={{ scale: 1.02 }}
                  >
                    <div className="diagram-thumb-header">
                      <span className="diagram-thumb-type">{d.diagram_type.replace('_', ' ')}</span>
                    </div>
                    <p className="diagram-thumb-desc">{d.description}</p>
                    <span className="diagram-thumb-count">
                      {d.involved_components?.length || 0} components
                    </span>
                  </motion.div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {!loading && diagrams.length === 0 && !error && (
        <div className="empty-state">
          <GitBranch size={40} />
          <h3>No diagrams yet</h3>
          <p>Make sure the repository has been ingested successfully.</p>
        </div>
      )}
    </div>
  )
}
