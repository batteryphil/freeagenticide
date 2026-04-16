import { useState, useCallback, useRef, useEffect } from 'react'
import Editor from '@monaco-editor/react'
import { useRunner } from '../hooks/useRunner'
import { RunPanel } from './RunPanel'

const LANGUAGES = [
  'python', 'javascript', 'typescript', 'bash',
  'html', 'rust', 'go', 'json', 'yaml', 'markdown', 'plaintext',
]

const STARTER: Record<string, string> = {
  python: `# Antigravity — Python Runner
# Write code here and press ▶ Run

def main():
    print("Hello from Antigravity!")
    for i in range(5):
        print(f"  Line {i + 1}")

if __name__ == "__main__":
    main()
`,
  html: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Antigravity Output</title>
  <style>
    body { font-family: sans-serif; background: #1e1e1e; color: #ccc;
           display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    h1 { color: #4fc1ff; }
  </style>
</head>
<body>
  <div>
    <h1>Hello from Antigravity!</h1>
    <p>Edit this HTML and click ▶ Run to see it render.</p>
  </div>
</body>
</html>`,
  javascript: `// Antigravity — Node.js Runner
const greeting = "Hello from Node.js!";
console.log(greeting);
for (let i = 0; i < 5; i++) {
  console.log(\`  Line \${i + 1}\`);
}`,
  bash: `#!/bin/bash
echo "Hello from Antigravity!"
for i in {1..5}; do
  echo "  Line $i"
done`,
}

import type { RunEvent } from '../hooks/useRunner'
import type { EditorUpdate } from '../hooks/useAgentWS'

interface Props {
  /** Code + language written by the agent via write_to_editor tool */
  agentEditorUpdate?: EditorUpdate | null
  /** Live terminal events emitted by the agent's run_in_ui tool */
  agentTerminalEvents?: RunEvent[]
  /** True while the agent's run_in_ui subprocess is active */
  agentTerminalRunning?: boolean
  onClearAgentTerminal?: () => void
}

// Languages that can be run
const RUNNABLE = new Set(['python', 'javascript', 'typescript', 'bash', 'html'])


export function MonacoPane({
  agentEditorUpdate,
  agentTerminalEvents = [],
  agentTerminalRunning = false,
  onClearAgentTerminal,
}: Props) {
  const [language, setLanguage] = useState('python')
  const [value, setValue] = useState(STARTER['python'])
  const [copyLabel, setCopyLabel] = useState('Copy')
  const [panelOpen, setPanelOpen] = useState(false)
  const [panelHeight, setPanelHeight] = useState(220)
  const [agentMode, setAgentMode] = useState(false)  // true while agent controls editor
  const draggingPanel = useRef(false)
  const panelDivRef = useRef<HTMLDivElement>(null)

  const { output: manualOutput, running: manualRunning, htmlUrl, run, killProcess, clearOutput } = useRunner()

  // ── Sync editor when agent writes code ──────────────────────────────────
  useEffect(() => {
    if (!agentEditorUpdate) return
    setLanguage(agentEditorUpdate.language || 'python')
    setValue(agentEditorUpdate.code || '')
    setAgentMode(true)
    setPanelOpen(true)   // auto-open terminal when agent writes code
  }, [agentEditorUpdate])

  // Auto-open panel when agent starts running
  useEffect(() => {
    if (agentTerminalRunning || agentTerminalEvents.length > 0) {
      setPanelOpen(true)
    }
  }, [agentTerminalRunning, agentTerminalEvents])

  // If agent finishes and user manually changes language, exit agent mode
  const handleLangChange = useCallback((lang: string) => {
    setLanguage(lang)
    setValue(STARTER[lang] ?? `// ${lang} code here\n`)
    setPanelOpen(false)
    clearOutput()
    setAgentMode(false)
  }, [clearOutput])

  // Use agent terminal output when agent is controlling; fall back to manual
  const isAgentControlled = agentMode && (agentTerminalEvents.length > 0 || agentTerminalRunning)
  const activeOutput = isAgentControlled ? agentTerminalEvents : manualOutput
  const activeRunning = isAgentControlled ? agentTerminalRunning : manualRunning
  const activeHtmlUrl = isAgentControlled
    ? (agentTerminalEvents.find(e => (e as any).url) as any)?.url ?? null
    : htmlUrl

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(value).then(() => {
      setCopyLabel('Copied!')
      setTimeout(() => setCopyLabel('Copy'), 1800)
    })
  }, [value])

  const handleRun = useCallback(() => {
    setAgentMode(false)  // user takes over
    setPanelOpen(true)
    run(value, language)
  }, [value, language, run])

  const handleOpenTab = useCallback((url: string) => {
    window.open(url, '_blank')
  }, [])

  const handleKill = useCallback(() => {
    if (isAgentControlled) {
      onClearAgentTerminal?.()
    } else {
      killProcess()
    }
  }, [isAgentControlled, killProcess, onClearAgentTerminal])

  const handleClear = useCallback(() => {
    if (isAgentControlled) {
      onClearAgentTerminal?.()
    } else {
      clearOutput()
    }
    setPanelOpen(false)
    setAgentMode(false)
  }, [isAgentControlled, clearOutput, onClearAgentTerminal])

  // ── Resize panel by dragging its top edge ────────────────────────────────
  const onPanelDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    draggingPanel.current = true
    const startY = e.clientY
    const startH = panelHeight

    const onMove = (ev: MouseEvent) => {
      if (!draggingPanel.current) return
      const delta = startY - ev.clientY
      setPanelHeight(Math.max(100, Math.min(startH + delta, 600)))
    }
    const onUp = () => {
      draggingPanel.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [panelHeight])

  const canRun = RUNNABLE.has(language)

  return (
    <div className="editor-pane" id="monaco-pane" style={{ flexDirection: 'column' }}>
      {/* Editor header */}
      <div className="editor-pane-header">
        <span className="editor-pane-title">
          Editor
          {agentMode && (
            <span
              title="Agent is controlling this editor"
              style={{
                marginLeft: 8, fontSize: 10, color: '#4ec9b0',
                background: '#1a3a2e', border: '1px solid #2d7a2d',
                borderRadius: 4, padding: '1px 6px', letterSpacing: '0.05em',
              }}
            >
              🤖 Agent
            </span>
          )}
        </span>

        <select
          id="lang-select"
          className="lang-select"
          value={language}
          onChange={e => handleLangChange(e.target.value)}
          aria-label="Programming language"
        >
          {LANGUAGES.map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>

        <button
          id="btn-copy"
          className={`btn-copy ${copyLabel === 'Copied!' ? 'copied' : ''}`}
          onClick={handleCopy}
          title="Copy editor contents"
        >
          {copyLabel}
        </button>

        {canRun && (
          <button
            id="btn-run"
            className={`btn-run ${activeRunning ? 'running' : ''}`}
            onClick={activeRunning ? handleKill : handleRun}
            title={activeRunning ? 'Stop process' : `Run ${language} code`}
          >
            {activeRunning ? '■ Stop' : '▶ Run'}
          </button>
        )}
      </div>

      {/* Monaco editor */}
      <div className="editor-container" style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          language={language}
          value={value}
          onChange={v => setValue(v ?? '')}
          theme="vs-dark"
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Consolas', monospace",
            fontLigatures: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            lineNumbers: 'on',
            renderLineHighlight: 'line',
            wordWrap: 'off',
            tabSize: 4,
            insertSpaces: true,
            automaticLayout: true,
            padding: { top: 10, bottom: 10 },
            smoothScrolling: true,
            cursorBlinking: 'smooth',
            cursorStyle: 'line',
            bracketPairColorization: { enabled: true },
            guides: { bracketPairs: true },
            suggest: { showKeywords: true, showSnippets: true },
          }}
        />
      </div>

      {/* Drag handle + Run panel */}
      {panelOpen && (
        <>
          <div
            ref={panelDivRef}
            className="panel-drag-handle"
            onMouseDown={onPanelDragStart}
            title="Drag to resize terminal"
          />
          <div style={{ height: panelHeight, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
            <RunPanel
              output={activeOutput}
              running={activeRunning}
              htmlUrl={activeHtmlUrl}
              onKill={handleKill}
              onClear={handleClear}
              onOpenInTab={handleOpenTab}
            />
          </div>
        </>
      )}
    </div>
  )
}
