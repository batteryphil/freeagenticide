import type { ProviderInfo } from '../types'

interface Props {
  providers: ProviderInfo[]
  totalCost: number
  tokensIn: number
  tokensOut: number
  connected: boolean
  streaming: boolean
  activeModel?: string
  onModelClick?: () => void
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0.00'
  if (usd < 0.001) return '<$0.001'
  return `$${usd.toFixed(4)}`
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function StatusBar({
  providers, totalCost, tokensIn, tokensOut,
  connected, streaming, activeModel, onModelClick,
}: Props) {
  const available = providers.filter(p => p.available)

  return (
    <div className="status-bar" id="status-bar" role="status" aria-live="polite">
      {/* Connection */}
      <div className="status-item">
        <span className={`dot ${connected ? 'green' : 'red'}`} />
        {connected ? (streaming ? 'Streaming…' : 'Ready') : 'Disconnected'}
      </div>

      {/* Active model — clickable to open model library */}
      {activeModel && (
        <div
          className="status-item"
          style={{ cursor: onModelClick ? 'pointer' : 'default' }}
          onClick={onModelClick}
          title="Change model"
          id="status-active-model"
        >
          ⚡ {activeModel}
        </div>
      )}

      {/* Provider count */}
      <div className="status-item">
        ✅ {available.length}/{providers.length} providers
      </div>

      <div className="status-spacer" />

      {/* Token usage */}
      {(tokensIn > 0 || tokensOut > 0) && (
        <div className="status-item tokens">
          ↑{formatTokens(tokensIn)} ↓{formatTokens(tokensOut)}
        </div>
      )}

      {/* Cost */}
      <div className="status-item cost">
        {formatCost(totalCost)}
      </div>
    </div>
  )
}
