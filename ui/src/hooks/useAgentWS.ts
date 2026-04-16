import { useState, useEffect, useRef, useCallback } from 'react'
import type {
  ServerMessage,
  ChunkMessage,
  StatusMessage,
  ProviderInfo,
  ChatTurn,
} from '../types'

const WS_URL = `ws://${window.location.host}/ws/chat`
const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECTS = 10

let _turnId = 0
const nextId = () => String(++_turnId)

import type { RunEvent } from './useRunner'

export interface EditorUpdate {
  code: string
  language: string
}

export interface UseAgentWS {
  turns: ChatTurn[]
  providers: ProviderInfo[]
  totalCost: number
  tokensIn: number
  tokensOut: number
  connected: boolean
  streaming: boolean
  /** Code + language the agent wrote to the editor via write_to_editor tool */
  agentEditorUpdate: EditorUpdate | null
  /** Terminal events fired by the agent via run_in_ui tool */
  agentTerminalEvents: RunEvent[]
  agentTerminalRunning: boolean
  sendMessage: (text: string) => void
  interrupt: () => void
  clearHistory: () => void
  clearAgentTerminal: () => void
}

/**
 * useAgentWS — manages the WebSocket connection to the FastAPI backend.
 *
 * Translates ChunkMessages into ChatTurns, accumulates streaming text,
 * and exposes send/interrupt/clear actions to the UI.
 */
export function useAgentWS(): UseAgentWS {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [totalCost, setTotalCost] = useState(0)
  const [tokensIn, setTokensIn] = useState(0)
  const [tokensOut, setTokensOut] = useState(0)
  const [connected, setConnected] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [agentEditorUpdate, setAgentEditorUpdate] = useState<EditorUpdate | null>(null)
  const [agentTerminalEvents, setAgentTerminalEvents] = useState<RunEvent[]>([])
  const [agentTerminalRunning, setAgentTerminalRunning] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCount = useRef(0)
  const streamingTurnId = useRef<string | null>(null)

  // ── Connection management ──────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      reconnectCount.current = 0
    }

    ws.onclose = () => {
      setConnected(false)
      setStreaming(false)
      if (reconnectCount.current < MAX_RECONNECTS) {
        reconnectCount.current++
        setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg: ServerMessage = JSON.parse(event.data as string)
        handleServerMessage(msg)
      } catch {
        // ignore malformed frames
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  // ── Server message handler ─────────────────────────────────────────────────

  const handleServerMessage = useCallback((msg: ServerMessage) => {
    switch (msg.type) {
      case 'chunk':
        handleChunk(msg as ChunkMessage)
        break
      case 'status':
        handleStatus(msg as StatusMessage)
        break
      case 'done':
        setStreaming(false)
        streamingTurnId.current = null
        setTotalCost(msg.total_cost_usd)
        setTurns(prev =>
          prev.map(t =>
            t.id === streamingTurnId.current ? { ...t, isStreaming: false } : t
          )
        )
        break
      case 'error':
        setStreaming(false)
        streamingTurnId.current = null
        setTurns(prev => [
          ...prev,
          {
            id: nextId(),
            role: 'error',
            content: msg.message,
            timestamp: Date.now(),
          },
        ])
        break

      // ── Agent UI action messages ───────────────────────────────────────
      case 'editor_update':
        // Agent called write_to_editor — push code to Monaco
        setAgentEditorUpdate({ code: msg.code ?? '', language: msg.language ?? 'python' })
        break

      case 'terminal_start':
        // Agent is about to run code — clear previous output, mark running
        setAgentTerminalEvents([])
        setAgentTerminalRunning(true)
        break

      case 'terminal_event': {
        const evt: RunEvent = msg.event ?? msg
        setAgentTerminalEvents(prev => [...prev, evt])
        if (evt.type === 'exit' || evt.type === 'stream_end') {
          setAgentTerminalRunning(false)
        }
        break
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleChunk = useCallback((chunk: ChunkMessage) => {
    setStreaming(true)

    setTurns(prev => {
      // Determine target turn — tool calls get their own separate turn
      const isTool = chunk.is_tool_call || chunk.is_tool_result
      const lastTurn = prev[prev.length - 1]

      // Append to existing streaming turn if roles match
      if (
        streamingTurnId.current &&
        lastTurn?.id === streamingTurnId.current &&
        !isTool
      ) {
        return prev.map(t =>
          t.id === streamingTurnId.current
            ? { ...t, content: t.content + chunk.text }
            : t
        )
      }

      // Create new turn
      const role: ChatTurn['role'] = isTool
        ? chunk.is_tool_call
          ? 'tool'
          : 'tool'
        : 'assistant'

      const newTurn: ChatTurn = {
        id: nextId(),
        role,
        content: chunk.text,
        agentName: chunk.agent_name,
        agentDepth: chunk.depth,
        isToolCall: chunk.is_tool_call,
        isToolResult: chunk.is_tool_result,
        isStreaming: true,
        timestamp: Date.now(),
      }

      if (!isTool) streamingTurnId.current = newTurn.id
      return [...prev, newTurn]
    })
  }, [])

  const handleStatus = useCallback((msg: StatusMessage) => {
    setProviders(msg.providers)
    setTotalCost(msg.total_cost_usd)
    setTokensIn(msg.tokens_in)
    setTokensOut(msg.tokens_out)
  }, [])

  // ── Actions ───────────────────────────────────────────────────────────────

  const sendMessage = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    if (!text.trim()) return

    // Add user turn immediately for instant feedback
    setTurns(prev => [
      ...prev,
      {
        id: nextId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      },
    ])

    wsRef.current.send(JSON.stringify({ type: 'chat', message: text }))
  }, [])

  const interrupt = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'interrupt' }))
    setStreaming(false)
  }, [])

  const clearHistory = useCallback(() => {
    setTurns([])
    setTotalCost(0)
    setTokensIn(0)
    setTokensOut(0)
  }, [])

  const clearAgentTerminal = useCallback(() => {
    setAgentTerminalEvents([])
    setAgentTerminalRunning(false)
  }, [])

  return {
    turns,
    providers,
    totalCost,
    tokensIn,
    tokensOut,
    connected,
    streaming,
    agentEditorUpdate,
    agentTerminalEvents,
    agentTerminalRunning,
    sendMessage,
    interrupt,
    clearHistory,
    clearAgentTerminal,
  }
}
