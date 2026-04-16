import type { ProviderInfo } from '../types'

interface Props {
  providers: ProviderInfo[]
}

export function ProviderSidebar({ providers }: Props) {
  const available = providers.filter(p => p.available)
  const unavailable = providers.filter(p => !p.available)

  return (
    <div className="provider-sidebar" id="provider-sidebar">
      <div className="provider-sidebar-header">Providers</div>
      <div className="provider-list">
        {providers.length === 0 && (
          <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: 11 }}>
            Checking…
          </div>
        )}
        {available.map(p => (
          <div key={p.name} className="provider-item" title={p.model ?? ''}>
            <span className="dot green" />
            <span className="provider-name">{p.name}</span>
            {p.latency_ms != null && (
              <span className="provider-latency">{Math.round(p.latency_ms)}ms</span>
            )}
          </div>
        ))}
        {unavailable.map(p => (
          <div key={p.name} className="provider-item" style={{ opacity: 0.45 }}>
            <span className="dot red" />
            <span className="provider-name">{p.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
