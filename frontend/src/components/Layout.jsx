import React, { useState } from 'react'
import { Outlet, Link, useLocation, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Cpu, MessageSquare, FolderOpen, GitBranch,
  Activity, Home, ChevronRight, Zap, Globe
} from 'lucide-react'
import { useStore } from '../store'

const NAV_ITEMS = [
  { icon: Home, label: 'Overview', path: '' },
  { icon: MessageSquare, label: 'Chat', path: '/chat' },
  { icon: FolderOpen, label: 'Explorer', path: '/explorer' },
  { icon: GitBranch, label: 'Architecture', path: '/architecture' },
  { icon: Activity, label: 'Health', path: '/health' },
]

export default function Layout() {
  const location = useLocation()
  const { repoId } = useParams()
  const currentRepo = useStore(s => s.currentRepo)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const isHome = !repoId

  return (
    <div className="layout">
      {/* Sidebar */}
      <motion.aside
        className="sidebar"
        animate={{ width: sidebarOpen ? 240 : 64 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      >
        {/* Logo */}
        <div className="sidebar-logo">
          <div className="logo-icon">
            <Cpu size={20} />
          </div>
          <AnimatePresence>
            {sidebarOpen && (
              <motion.span
                className="logo-text"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
              >
                CodeOracle
              </motion.span>
            )}
          </AnimatePresence>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <motion.div animate={{ rotate: sidebarOpen ? 180 : 0 }}>
              <ChevronRight size={14} />
            </motion.div>
          </button>
        </div>

        {/* Repo selector link */}
        <Link to="/" className={`nav-home ${isHome ? 'active' : ''}`}>
          <Globe size={16} />
          {sidebarOpen && <span>Repositories</span>}
        </Link>

        {/* Per-repo nav */}
        {repoId && (
          <>
            <div className="nav-section-label">
              {sidebarOpen && <span>Current Repo</span>}
            </div>
            {NAV_ITEMS.map(({ icon: Icon, label, path }) => {
              const fullPath = `/repo/${repoId}${path}`
              const isActive = location.pathname === fullPath
              return (
                <Link key={path} to={fullPath} className={`nav-item ${isActive ? 'active' : ''}`}>
                  <Icon size={16} />
                  {sidebarOpen && <span>{label}</span>}
                  {isActive && (
                    <motion.div
                      className="nav-indicator"
                      layoutId="nav-indicator"
                    />
                  )}
                </Link>
              )
            })}
          </>
        )}

        {/* Status indicator */}
        <div className="sidebar-footer">
          <div className="status-dot active" />
          {sidebarOpen && <span className="status-text">System Online</span>}
        </div>
      </motion.aside>

      {/* Main content */}
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
