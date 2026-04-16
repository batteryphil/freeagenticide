import { useState, useMemo } from 'react'
import type { ModelEntry, PullProgress } from '../hooks/useModels'

interface Props {
  models: ModelEntry[]
  activeModel: string
  pullProgress: Record<string, PullProgress>
  onPull: (modelId: string) => void
  onDelete: (modelId: string) => void
  onActivate: (modelId: string) => void
  onClose: () => void
}

const TAG_COLORS: Record<string, string> = {
  coding:    '#569cd6',
  general:   '#4ec9b0',
  fast:      '#dcdcaa',
  reasoning: '#c586c0',
  minimal:   '#858585',
  custom:    '#9cdcfe',
  mamba:     '#f97583',
}

function formatSize(gb: number): string {
  if (gb < 1) return `${Math.round(gb * 1000)}MB`
  return `${gb.toFixed(1)}GB`
}

function ProgressBar({ progress }: { progress: PullProgress }) {
  const { status, completed = 0, total = 0 } = progress
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  if (status === 'done') {
    return <span style={{ color: 'var(--status-green)', fontSize: 11 }}>✓ Installed</span>
  }
  if (status === 'error') {
    return <span style={{ color: 'var(--text-error)', fontSize: 11 }}>✗ {progress.error ?? 'Error'}</span>
  }

  const label = total > 0
    ? `${pct}% — ${formatSize(completed / 1e9)} / ${formatSize(total / 1e9)}`
    : status

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 100, height: 4, background: 'var(--border)',
        borderRadius: 2, overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: 'var(--accent)',
          transition: 'width 0.2s ease',
        }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        {label}
      </span>
    </div>
  )
}

function ModelRow({
  model,
  active,
  pulling,
  progress,
  onPull,
  onDelete,
  onActivate,
}: {
  model: ModelEntry
  active: boolean
  pulling: boolean
  progress?: PullProgress
  onPull: () => void
  onDelete: () => void
  onActivate: () => void
}) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr auto',
      alignItems: 'start',
      padding: '10px 16px',
      borderBottom: '1px solid var(--border)',
      background: active ? 'rgba(0,120,212,0.1)' : 'transparent',
      transition: 'background 0.15s',
    }}>
      <div>
        {/* Model name + badges */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
          {active && (
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--status-green)',
              boxShadow: '0 0 4px var(--status-green)',
              flexShrink: 0,
            }} />
          )}
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
            {model.id}
          </span>
          {model.recommended && (
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: 'rgba(0,120,212,0.25)', color: 'var(--text-accent)',
              fontWeight: 700, letterSpacing: '0.05em',
            }}>
              RECOMMENDED
            </span>
          )}
          {model.installed && !active && (
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: 'rgba(78,201,176,0.15)', color: 'var(--status-green)',
            }}>
              installed
            </span>
          )}
        </div>

        {/* Family + size info */}
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          {model.family} ·{' '}
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {formatSize(model.installed_size_gb ?? model.size_gb)}
          </span>
          {model.ram_gb && (
            <span> · ~{model.ram_gb}GB RAM</span>
          )}
        </div>

        {/* Description */}
        <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginBottom: 5, lineHeight: 1.4 }}>
          {model.desc}
        </div>

        {/* Tags */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4 }}>
          {model.tags.map(tag => (
            <span key={tag} style={{
              fontSize: 10, padding: '1px 5px', borderRadius: 3,
              border: `1px solid ${TAG_COLORS[tag] ?? '#555'}33`,
              color: TAG_COLORS[tag] ?? 'var(--text-muted)',
            }}>
              {tag}
            </span>
          ))}
        </div>

        {/* Pull progress */}
        {pulling && progress && <ProgressBar progress={progress} />}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 12 }}>
        {model.installed ? (
          <>
            {!active && (
              <button
                className="btn-model-action primary"
                onClick={onActivate}
                title="Use this model"
              >
                Use
              </button>
            )}
            {active && (
              <span style={{ fontSize: 11, color: 'var(--status-green)', textAlign: 'center' }}>Active</span>
            )}
            <button
              className="btn-model-action danger"
              onClick={onDelete}
              title="Delete model"
            >
              Delete
            </button>
          </>
        ) : (
          <button
            className="btn-model-action primary"
            onClick={onPull}
            disabled={pulling}
            title="Download model"
          >
            {pulling ? '…' : '↓ Pull'}
          </button>
        )}
      </div>
    </div>
  )
}

const ALL_TAGS = ['all', 'coding', 'general', 'fast', 'reasoning', 'minimal', 'mamba']


export function ModelManager({
  models,
  activeModel,
  pullProgress,
  onPull,
  onDelete,
  onActivate,
  onClose,
}: Props) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [showInstalled, setShowInstalled] = useState(false)

  const visible = useMemo(() => {
    return models.filter(m => {
      if (showInstalled && !m.installed) return false
      if (filter !== 'all' && !m.tags.includes(filter)) return false
      if (search && !m.id.toLowerCase().includes(search.toLowerCase()) &&
          !m.desc.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [models, filter, search, showInstalled])

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: 'var(--bg-sidebar)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        width: 'min(800px, 95vw)',
        maxHeight: '85vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 16px 10px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>⚡ Model Library</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {models.filter(m => m.installed).length} installed · {models.length} available
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: 'var(--text-muted)',
              fontSize: 18, cursor: 'pointer', lineHeight: 1,
            }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Filters */}
        <div style={{
          display: 'flex', gap: 8, padding: '10px 16px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0, flexWrap: 'wrap', alignItems: 'center',
        }}>
          <input
            type="text"
            placeholder="Search models…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, color: 'var(--text-primary)', fontFamily: 'var(--font-ui)',
              fontSize: 12, padding: '4px 10px', outline: 'none', width: 160,
            }}
          />
          {ALL_TAGS.map(tag => (
            <button
              key={tag}
              onClick={() => setFilter(tag)}
              style={{
                background: filter === tag ? 'var(--accent)' : 'var(--bg-input)',
                border: '1px solid var(--border)',
                borderRadius: 4, color: filter === tag ? '#fff' : 'var(--text-secondary)',
                fontSize: 11, fontFamily: 'var(--font-ui)',
                padding: '3px 10px', cursor: 'pointer', transition: 'all 0.1s',
              }}
            >
              {tag}
            </button>
          ))}
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', marginLeft: 'auto' }}>
            <input
              type="checkbox"
              checked={showInstalled}
              onChange={e => setShowInstalled(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Installed only
          </label>
        </div>

        {/* Model list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {visible.length === 0 && (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
              No models match your filters.
            </div>
          )}
          {visible.map(model => (
            <ModelRow
              key={model.id}
              model={model}
              active={model.id === activeModel}
              pulling={!!pullProgress[model.id] && pullProgress[model.id].status !== 'done'}
              progress={pullProgress[model.id]}
              onPull={() => onPull(model.id)}
              onDelete={() => onDelete(model.id)}
              onActivate={() => onActivate(model.id)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
