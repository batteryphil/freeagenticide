import { useRef, useEffect, useState, useCallback, type MouseEvent } from 'react'
import { useAgentWS } from './hooks/useAgentWS'
import { useModels } from './hooks/useModels'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import { MonacoPane } from './components/MonacoPane'
import { ProviderSidebar } from './components/ProviderSidebar'
import { StatusBar } from './components/StatusBar'
import { ModelManager } from './components/ModelManager'
import './index.css'

const CHAT_MIN_PX = 280
const EDITOR_MIN_PX = 200
const DEFAULT_CHAT_PERCENT = 45

export default function App() {
  const {
    turns, providers, totalCost, tokensIn, tokensOut,
    connected, streaming,
    sendMessage, interrupt, clearHistory,
    agentEditorUpdate, agentTerminalEvents, agentTerminalRunning, clearAgentTerminal,
  } = useAgentWS()

  const {
    models, activeModel, pullProgress,
    pullModel, deleteModel, activateModel,
  } = useModels()

  const [showModels, setShowModels] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll on new turns
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  // ── Resizable split ───────────────────────────────────────────────────────
  const mainRef = useRef<HTMLDivElement>(null)
  const [chatWidthPct, setChatWidthPct] = useState(DEFAULT_CHAT_PERCENT)
  const dragging = useRef(false)
  const dividerRef = useRef<HTMLDivElement>(null)

  const onDividerMouseDown = useCallback((e: MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    dividerRef.current?.classList.add('dragging')
  }, [])

  useEffect(() => {
    const onMove = (e: globalThis.MouseEvent) => {
      if (!dragging.current || !mainRef.current) return
      const rect = mainRef.current.getBoundingClientRect()
      const rawPx = e.clientX - rect.left
      const clampedPx = Math.max(CHAT_MIN_PX, Math.min(rawPx, rect.width - EDITOR_MIN_PX - 4))
      setChatWidthPct((clampedPx / rect.width) * 100)
    }
    const onUp = () => {
      dragging.current = false
      dividerRef.current?.classList.remove('dragging')
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  return (
    <div className="app-shell">
      {/* Title bar */}
      <div className="app-titlebar">
        <span className="logo">Anti<span>gravity</span></span>
        <span
          className={`connection-dot ${connected ? 'connected' : 'disconnected'}`}
          title={connected ? 'Connected' : 'Disconnected'}
        />

        {/* Active model chip — click to open model library */}
        {activeModel && (
          <button
            id="btn-active-model"
            className="model-chip"
            onClick={() => setShowModels(true)}
            title="Change model"
          >
            ⚡ {activeModel}
          </button>
        )}

        <span className="title-spacer" />

        <button
          id="btn-models"
          className="btn-clear"
          onClick={() => setShowModels(true)}
          title="Open model library"
        >
          Models
        </button>
        <button
          id="btn-clear"
          className="btn-clear"
          onClick={clearHistory}
          disabled={streaming}
          title="Clear conversation"
        >
          Clear
        </button>
      </div>

      {/* Main area */}
      <div className="app-main" ref={mainRef}>
        <ProviderSidebar providers={providers} />

        <div
          className="chat-panel"
          id="chat-panel"
          style={{ width: `${chatWidthPct}%`, minWidth: CHAT_MIN_PX }}
        >
          <div className="chat-panel-header">Chat</div>
          <ChatMessages turns={turns} messagesEndRef={messagesEndRef} />
          <ChatInput
            onSend={sendMessage}
            onInterrupt={interrupt}
            streaming={streaming}
            connected={connected}
          />
        </div>

        <div
          ref={dividerRef}
          className="split-divider"
          onMouseDown={onDividerMouseDown}
          title="Drag to resize"
          role="separator"
          aria-label="Resize panels"
        />

        <div style={{ flex: 1, minWidth: EDITOR_MIN_PX, overflow: 'hidden', display: 'flex' }}>
          <MonacoPane
            agentEditorUpdate={agentEditorUpdate}
            agentTerminalEvents={agentTerminalEvents}
            agentTerminalRunning={agentTerminalRunning}
            onClearAgentTerminal={clearAgentTerminal}
          />
        </div>
      </div>

      <StatusBar
        providers={providers}
        totalCost={totalCost}
        tokensIn={tokensIn}
        tokensOut={tokensOut}
        connected={connected}
        streaming={streaming}
        activeModel={activeModel}
        onModelClick={() => setShowModels(true)}
      />

      {/* Model library modal */}
      {showModels && (
        <ModelManager
          models={models}
          activeModel={activeModel}
          pullProgress={pullProgress}
          onPull={pullModel}
          onDelete={deleteModel}
          onActivate={activateModel}
          onClose={() => setShowModels(false)}
        />
      )}
    </div>
  )
}
