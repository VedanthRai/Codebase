import { create } from 'zustand'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export const useStore = create((set, get) => ({
  // Current repository
  currentRepo: null,
  repos: [],

  // UI state
  isIngesting: false,
  ingestProgress: 0,
  ingestMessage: '',
  ingestError: null,

  // Chat state
  messages: [],
  isQuerying: false,

  // Set current repo
  setCurrentRepo: (repo) => set({ currentRepo: repo }),

  // Load all repos
  loadRepos: async () => {
    try {
      const { data } = await axios.get(`${API}/api/repos`)
      set({ repos: data.repos })
    } catch (e) {
      console.error('Failed to load repos', e)
    }
  },

  // Load single repo
  loadRepo: async (repoId) => {
    try {
      const { data } = await axios.get(`${API}/api/repos/${repoId}`)
      set({ currentRepo: data })
      return data
    } catch (e) {
      console.error('Failed to load repo', e)
      return null
    }
  },

  // Ingest a new repository
  ingestRepo: async (githubUrl, branch = 'main') => {
    set({ isIngesting: true, ingestProgress: 0, ingestMessage: 'Starting...', ingestError: null })

    try {
      const { data: job } = await axios.post(`${API}/api/repos/ingest`, {
        github_url: githubUrl,
        branch,
      })

      // Poll for progress
      const jobId = job.job_id
      const repoId = job.repo_id

      await new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
          try {
            const { data: status } = await axios.get(`${API}/api/jobs/${jobId}`)
            set({ ingestProgress: status.progress, ingestMessage: status.message })

            if (status.status === 'done') {
              clearInterval(interval)
              resolve(repoId)
            } else if (status.status === 'error') {
              clearInterval(interval)
              reject(new Error(status.error || 'Ingestion failed'))
            }
          } catch (e) {
            clearInterval(interval)
            reject(e)
          }
        }, 1000)
      })

      // Load repo data
      await get().loadRepos()
      const repo = await get().loadRepo(repoId)
      set({ isIngesting: false, ingestProgress: 100 })
      return repoId
    } catch (e) {
      set({ isIngesting: false, ingestError: e.message })
      throw e
    }
  },

  // Query
  query: async (repoId, queryText, mode = null, includeHistory = true) => {
    set({ isQuerying: true })
    const history = includeHistory
      ? get().messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
      : []

    // Add user message
    set(state => ({
      messages: [...state.messages, {
        id: Date.now(),
        role: 'user',
        content: queryText,
        timestamp: new Date(),
      }]
    }))

    try {
      const { data } = await axios.post(`${API}/api/query`, {
        repo_id: repoId,
        query: queryText,
        mode,
        conversation_history: history,
        include_diagrams: true,
      })

      set(state => ({
        messages: [...state.messages, {
          id: Date.now() + 1,
          role: 'assistant',
          content: data.response,
          diagrams: data.diagrams || [],
          verification: data.verification,
          chunks: data.retrieved_chunks || [],
          intent: data.intent,
          enhanced_query: data.enhanced_query,
          processing_time: data.processing_time_ms,
          tldr: data.tldr || '',
          takeaways: data.takeaways || [],
          suggested_questions: data.suggested_questions || [],
          timestamp: new Date(),
        }],
        isQuerying: false,
      }))

      return data
    } catch (e) {
      set(state => ({
        messages: [...state.messages, {
          id: Date.now() + 1,
          role: 'error',
          content: e.response?.data?.detail || e.message,
          timestamp: new Date(),
        }],
        isQuerying: false,
      }))
      throw e
    }
  },

  clearMessages: () => set({ messages: [] }),
}))
