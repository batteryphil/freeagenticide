/** WebSocket message protocol — mirrors ag/server/models.py */

export interface ChunkMessage {
  type: 'chunk'
  text: string
  agent_name: string
  depth: number
  is_tool_call: boolean
  is_tool_result: boolean
  is_final: boolean
}

export interface ProviderInfo {
  name: string
  available: boolean
  model?: string
  latency_ms?: number
}

export interface StatusMessage {
  type: 'status'
  providers: ProviderInfo[]
  total_cost_usd: number
  tokens_in: number
  tokens_out: number
  active_model?: string
  active_provider?: string
}

export interface ErrorMessage {
  type: 'error'
  message: string
  recoverable: boolean
}

export interface DoneMessage {
  type: 'done'
  total_cost_usd: number
}

// ── Agent UI action messages ──────────────────────────────────────────────────

export interface EditorUpdateMessage {
  type: 'editor_update'
  code: string
  language: string
}

export interface TerminalStartMessage {
  type: 'terminal_start'
  language: string
  filename: string
}

export interface TerminalEventMessage {
  type: 'terminal_event'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  event: any
}

export type ServerMessage =
  | ChunkMessage
  | StatusMessage
  | ErrorMessage
  | DoneMessage
  | EditorUpdateMessage
  | TerminalStartMessage
  | TerminalEventMessage


// ── Chat turn model ──────────────────────────────────────────────────────────

export type TurnRole = 'user' | 'assistant' | 'tool' | 'error'

export interface ChatTurn {
  id: string
  role: TurnRole
  content: string          // accumulated text
  agentName?: string
  agentDepth?: number
  isToolCall?: boolean
  isToolResult?: boolean
  isStreaming?: boolean
  timestamp: number
}
