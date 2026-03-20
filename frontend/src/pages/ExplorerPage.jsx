import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search, FileCode, Code2, Package, Zap,
  ChevronDown, ChevronRight, Filter
} from 'lucide-react'
import axios from 'axios'
import { useStore } from '../store'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const LANG_COLORS = {
  python: '#3776ab',
  javascript: '#f7df1e',
  typescript: '#3178c6',
  java: '#b07219',
  cpp: '#f34b7d',
  go: '#00acd7',
  rust: '#dea584',
  unknown: '#64748b',
}

const COMPLEXITY_COLOR = (c) => {
  if (c < 5) return '#10b981'
  if (c < 15) return '#f59e0b'
  return '#ef4444'
}

function FileRow({ file, onSelect, selected }) {
  const langColor = LANG_COLORS[file.language] || '#64748b'
  const complexColor = COMPLEXITY_COLOR(file.complexity)

  return (
    <motion.div
      className={`file-row ${selected ? 'selected' : ''}`}
      onClick={() => onSelect(file)}
      whileHover={{ backgroundColor: 'var(--surface-hover)' }}
    >
      <div className="file-row-main">
        <span className="lang-dot" style={{ backgroundColor: langColor }} />
        <span className="file-path">{file.path}</span>
      </div>
      <div className="file-row-meta">
        {file.functions > 0 && (
          <span className="meta-badge functions">
            <Code2 size={10} />
            {file.functions}
          </span>
        )}
        {file.classes > 0 && (
          <span className="meta-badge classes">
            <Package size={10} />
            {file.classes}
          </span>
        )}
        <span className="meta-badge complexity" style={{ color: complexColor }}>
          <Zap size={10} />
          {file.complexity}
        </span>
        <span className="meta-lines">{file.lines}L</span>
      </div>
    </motion.div>
  )
}

export default function ExplorerPage() {
  const { repoId } = useParams()
  const { currentRepo, loadRepo, query } = useStore()
  const [files, setFiles] = useState([])
  const [filtered, setFiltered] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [langFilter, setLangFilter] = useState('all')
  const [sortBy, setSortBy] = useState('complexity')
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileAnalysis, setFileAnalysis] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)

  useEffect(() => {
    if (!currentRepo) loadRepo(repoId)
    fetchFiles()
  }, [repoId])

  useEffect(() => {
    let result = [...files]
    if (search) {
      result = result.filter(f => f.path.toLowerCase().includes(search.toLowerCase()))
    }
    if (langFilter !== 'all') {
      result = result.filter(f => f.language === langFilter)
    }
    if (sortBy === 'complexity') {
      result.sort((a, b) => b.complexity - a.complexity)
    } else if (sortBy === 'functions') {
      result.sort((a, b) => b.functions - a.functions)
    } else if (sortBy === 'lines') {
      result.sort((a, b) => b.lines - a.lines)
    } else {
      result.sort((a, b) => a.path.localeCompare(b.path))
    }
    setFiltered(result)
  }, [files, search, langFilter, sortBy])

  const fetchFiles = async () => {
    setLoading(true)
    try {
      const { data } = await axios.get(`${API}/api/repos/${repoId}/files`)
      setFiles(data.files || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const analyzeFile = async (file) => {
    setSelectedFile(file)
    setAnalyzing(true)
    setFileAnalysis(null)
    try {
      const result = await query(
        repoId,
        `Analyze the file "${file.path}": explain its purpose, key functions, and any code quality issues.`,
        'explain',
        false,
      )
      setFileAnalysis(result)
    } catch (e) {
      console.error(e)
    } finally {
      setAnalyzing(false)
    }
  }

  const languages = ['all', ...new Set(files.map(f => f.language))]

  return (
    <div className="explorer-page">
      <div className="page-header">
        <div>
          <h1>File Explorer</h1>
          <p className="page-subtitle">{files.length} files analyzed</p>
        </div>
      </div>

      <div className="explorer-layout">
        {/* File list */}
        <div className="explorer-list">
          {/* Controls */}
          <div className="explorer-controls">
            <div className="search-wrap">
              <Search size={14} className="search-icon" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search files..."
                className="search-input"
              />
            </div>
            <div className="filter-row">
              <select
                value={langFilter}
                onChange={e => setLangFilter(e.target.value)}
                className="select-sm"
              >
                {languages.map(l => (
                  <option key={l} value={l}>{l === 'all' ? 'All languages' : l}</option>
                ))}
              </select>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="select-sm"
              >
                <option value="complexity">Sort: Complexity</option>
                <option value="functions">Sort: Functions</option>
                <option value="lines">Sort: Lines</option>
                <option value="path">Sort: Path</option>
              </select>
            </div>
          </div>

          {/* File rows */}
          <div className="file-list">
            {loading ? (
              <div className="list-loading">Loading files...</div>
            ) : filtered.length === 0 ? (
              <div className="list-empty">No files match your filter</div>
            ) : (
              filtered.map((file, i) => (
                <FileRow
                  key={file.path}
                  file={file}
                  selected={selectedFile?.path === file.path}
                  onSelect={analyzeFile}
                />
              ))
            )}
          </div>
        </div>

        {/* File detail panel */}
        <div className="explorer-detail">
          {!selectedFile ? (
            <div className="detail-empty">
              <FileCode size={32} />
              <p>Select a file to analyze</p>
            </div>
          ) : (
            <div className="detail-content">
              <div className="detail-header">
                <h3>{selectedFile.path.split('/').pop()}</h3>
                <span className="detail-path">{selectedFile.path}</span>
              </div>
              <div className="detail-stats">
                <span><Code2 size={12} /> {selectedFile.functions} functions</span>
                <span><Package size={12} /> {selectedFile.classes} classes</span>
                <span><Zap size={12} style={{ color: COMPLEXITY_COLOR(selectedFile.complexity) }} />
                  complexity {selectedFile.complexity}</span>
                <span>{selectedFile.lines} lines</span>
              </div>

              {analyzing ? (
                <div className="detail-loading">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    className="spinner-sm"
                  />
                  <p>Analyzing with AI agents...</p>
                </div>
              ) : fileAnalysis ? (
                <div className="detail-analysis">
                  <h4>AI Analysis</h4>
                  <div className="analysis-content">
                    {fileAnalysis.response}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
