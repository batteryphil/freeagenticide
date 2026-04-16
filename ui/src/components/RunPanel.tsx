import { useRef, useEffect } from 'react'
import type { RunEvent } from '../hooks/useRunner'

interface Props {
  output: RunEvent[]
  running: boolean
  htmlUrl: string | null
  onKill: () => void
  onClear: () => void
  onOpenInTab: (url: string) => void
}

function lineColor(type: RunEvent['type']): string {
  switch (type) {
    case 'stderr': return 'var(--text-error)'
    case 'system': return 'var(--text-accent)'
    case 'exit':   return 'var(--text-secondary)'
    default:       return 'var(--text-primary)'
  }
}

function linePrefix(type: RunEvent['type']): string {
  switch (type) {
    case 'stderr': return '!'
    case 'system': return '>'
    case 'exit':   return '‣'
    default:       return ' '
  }
}

/**
 * RunPanel — VS Code terminal-style output panel below the Monaco editor.
 *
 * Shows stdout (white), stderr (red), system messages (blue), and exit codes.
 * When an HTML program is run, renders it in an iframe beside the terminal.
 */
export function RunPanel({ output, running, htmlUrl, onKill, onClear, onOpenInTab }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll on new output
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [output])

  const hasOutput = output.length > 0

  return (
    <div className="run-panel" id="run-panel">
      {/* Panel header */}
      <div className="run-panel-header">
        <span className="run-panel-title">
          Terminal
          {running && (
            <span className="run-spinner" title="Running" />
          )}
        </span>

        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {htmlUrl && (
            <button
              className="btn-run-action"
              onClick={() => onOpenInTab(htmlUrl)}
              title="Open in new tab"
              id="btn-open-tab"
            >
              ⧉ New Tab
            </button>
          )}
          {running && (
            <button
              className="btn-run-action danger"
              onClick={onKill}
              id="btn-kill"
              title="Kill process"
            >
              ■ Kill
            </button>
          )}
          {hasOutput && !running && (
            <button
              className="btn-run-action"
              onClick={onClear}
              id="btn-clear-output"
              title="Clear output"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Content area — terminal + optional HTML iframe */}
      <div className="run-content" style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Terminal log */}
        <div
          className="run-terminal"
          style={{ flex: htmlUrl ? '0 0 40%' : 1, borderRight: htmlUrl ? '1px solid var(--border)' : 'none' }}
        >
          {!hasOutput && (
            <div style={{ color: 'var(--text-muted)', padding: '10px 14px', fontSize: 11 }}>
              Press ▶ Run to execute the editor code.
            </div>
          )}
          {output.map((evt, i) => (
            <div key={i} className={`run-line run-line-${evt.type}`}>
              <span className="run-line-prefix">{linePrefix(evt.type)}</span>
              <span style={{ color: lineColor(evt.type) }}>{evt.data}</span>
            </div>
          ))}
          {running && (
            <div className="run-line">
              <span className="run-line-prefix"> </span>
              <span className="run-cursor">█</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* HTML iframe (for web programs, games etc.) */}
        {htmlUrl && (
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fff' }}>
            <div style={{
              background: '#1a1a2e', padding: '2px 10px', fontSize: 10,
              color: 'var(--text-muted)', flexShrink: 0, display: 'flex',
              alignItems: 'center', gap: 8,
            }}>
              <span>🌐</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {window.location.origin}{htmlUrl}
              </span>
            </div>
            <iframe
              id="run-iframe"
              src={htmlUrl}
              title="Program output"
              style={{ flex: 1, border: 'none', width: '100%' }}
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        )}
      </div>
    </div>
  )
}
