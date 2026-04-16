import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatTurn } from '../types'

interface Props {
  turns: ChatTurn[]
  messagesEndRef: React.RefObject<HTMLDivElement | null>
}

function roleBadge(turn: ChatTurn): string {
  if (turn.role === 'tool') return turn.isToolCall ? 'tool call' : 'tool result'
  return turn.role
}

function depthLabel(depth?: number): string {
  if (!depth || depth === 0) return ''
  return '  '.repeat(depth) + '↳'
}

export function ChatMessages({ turns, messagesEndRef }: Props) {
  return (
    <div className="chat-messages" id="chat-messages">
      {turns.length === 0 && (
        <div style={{ padding: '24px 16px', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 2 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>⚡</div>
          <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Antigravity</div>
          <div style={{ fontSize: 12 }}>Multi-provider AI coding assistant</div>
          <div style={{ fontSize: 11, marginTop: 12, color: 'var(--text-muted)' }}>
            Type a message to start · Use the editor on the right for code
          </div>
        </div>
      )}

      {turns.map(turn => (
        <div
          key={turn.id}
          className={`chat-turn ${turn.role} ${turn.isToolResult ? 'result' : ''}`}
          id={`turn-${turn.id}`}
        >
          <div className="turn-meta">
            <span className={`turn-role-badge ${turn.role}`}>
              {roleBadge(turn)}
            </span>
            {(turn.agentDepth ?? 0) > 0 && (
              <span className="turn-agent-depth">
                {depthLabel(turn.agentDepth)} {turn.agentName}
              </span>
            )}
          </div>

          <div className={`turn-content ${turn.isStreaming ? 'streaming-cursor' : ''}`}>
            {turn.role === 'tool' ? (
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                {turn.content}
              </pre>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {turn.content}
              </ReactMarkdown>
            )}
          </div>
        </div>
      ))}

      <div ref={messagesEndRef} />
    </div>
  )
}
