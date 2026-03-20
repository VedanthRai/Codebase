import React, { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { Download, ZoomIn, ZoomOut } from 'lucide-react'

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#7c3aed',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#6d28d9',
    lineColor: '#94a3b8',
    secondaryColor: '#1e293b',
    tertiaryColor: '#0f172a',
    background: '#0f172a',
    mainBkg: '#1e293b',
    nodeBorder: '#6d28d9',
    clusterBkg: '#1e293b',
    titleColor: '#e2e8f0',
    edgeLabelBackground: '#1e293b',
  },
  flowchart: { curve: 'basis', padding: 20 },
  sequence: { actorMargin: 50, messageMargin: 20 },
})

let diagramCount = 0

export default function MermaidDiagram({ code, title, type }) {
  const ref = useRef(null)
  const [error, setError] = useState(null)
  const [zoom, setZoom] = useState(1)
  const [id] = useState(() => `mermaid-${++diagramCount}`)

  useEffect(() => {
    if (!ref.current || !code) return
    setError(null)

    const render = async () => {
      try {
        const cleanCode = code.trim()

        // Fast validation before rendering; mermaid.parse can throw detailed syntax errors.
        mermaid.parse(cleanCode)

        const { svg } = await mermaid.render(id, cleanCode)
        if (ref.current) {
          ref.current.innerHTML = svg
          // Make SVG responsive
          const svgEl = ref.current.querySelector('svg')
          if (svgEl) {
            svgEl.style.maxWidth = '100%'
            svgEl.style.height = 'auto'
          }
        }
      } catch (e) {
        setError(e?.message || String(e))
      }
    }
    render()
  }, [code, id])

  const downloadSVG = () => {
    const svgEl = ref.current?.querySelector('svg')
    if (!svgEl) return
    const blob = new Blob([svgEl.outerHTML], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title || 'diagram'}.svg`
    a.click()
    URL.revokeObjectURL(url)
  }

  const typeColors = {
    architecture: '#7c3aed',
    dependency: '#0891b2',
    sequence: '#059669',
    call_graph: '#d97706',
    class: '#be185d',
  }

  return (
    <div className="diagram-card">
      <div className="diagram-header">
        <div className="diagram-title">
          <span
            className="diagram-type-badge"
            style={{ backgroundColor: typeColors[type] || '#7c3aed' }}
          >
            {type?.replace('_', ' ')}
          </span>
          <span>{title}</span>
        </div>
        <div className="diagram-controls">
          <button onClick={() => setZoom(z => Math.max(0.5, z - 0.2))} className="icon-btn" title="Zoom out">
            <ZoomOut size={14} />
          </button>
          <span className="zoom-label">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(z => Math.min(2, z + 0.2))} className="icon-btn" title="Zoom in">
            <ZoomIn size={14} />
          </button>
          <button onClick={downloadSVG} className="icon-btn" title="Download SVG">
            <Download size={14} />
          </button>
        </div>
      </div>
      <div className="diagram-body" style={{ overflow: 'auto' }}>
        {error ? (
          <div className="diagram-error">
            <p>Diagram render failed</p>
            <pre className="diagram-code">{code}</pre>
          </div>
        ) : (
          <div
            ref={ref}
            style={{
              transform: `scale(${zoom})`,
              transformOrigin: 'top left',
              transition: 'transform 0.2s ease',
              minHeight: 200,
            }}
          />
        )}
      </div>
    </div>
  )
}
