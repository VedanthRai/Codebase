import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import RepositoryPage from './pages/RepositoryPage'
import ChatPage from './pages/ChatPage'
import ExplorerPage from './pages/ExplorerPage'
import ArchitecturePage from './pages/ArchitecturePage'
import HealthPage from './pages/HealthPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="repo/:repoId" element={<RepositoryPage />} />
          <Route path="repo/:repoId/chat" element={<ChatPage />} />
          <Route path="repo/:repoId/explorer" element={<ExplorerPage />} />
          <Route path="repo/:repoId/architecture" element={<ArchitecturePage />} />
          <Route path="repo/:repoId/health" element={<HealthPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
