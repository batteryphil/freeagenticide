import { useState, useEffect, useCallback, useRef } from 'react'

export interface ModelEntry {
  id: string
  family: string
  size_gb: number
  ram_gb: number | null
  desc: string
  tags: string[]
  recommended: boolean
  installed: boolean
  installed_size_gb: number | null
}

export interface PullProgress {
  status: string
  completed?: number
  total?: number
  error?: string
}

export interface UseModels {
  models: ModelEntry[]
  activeModel: string
  loading: boolean
  pullProgress: Record<string, PullProgress>
  refresh: () => Promise<void>
  pullModel: (modelId: string) => void
  deleteModel: (modelId: string) => Promise<void>
  activateModel: (modelId: string) => Promise<void>
}

export function useModels(): UseModels {
  const [models, setModels] = useState<ModelEntry[]>([])
  const [activeModel, setActiveModel] = useState('')
  const [loading, setLoading] = useState(false)
  const [pullProgress, setPullProgress] = useState<Record<string, PullProgress>>({})
  const activeSSE = useRef<Record<string, EventSource>>({})

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/models')
      const data = await resp.json()
      setModels(data.models ?? [])
      setActiveModel(data.active_model ?? '')
    } catch {
      // ignore — backend may not be ready
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    refresh()
  }, [refresh])

  const pullModel = useCallback((modelId: string) => {
    // Close any existing SSE for this model
    activeSSE.current[modelId]?.close()

    // Kick off the pull via POST then connect SSE
    fetch('/api/models/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    }).then(async resp => {
      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) return

      const readChunk = async () => {
        const { done, value } = await reader.read()
        if (done) {
          setPullProgress(prev => ({ ...prev, [modelId]: { status: 'done' } }))
          await refresh()
          return
        }

        const text = decoder.decode(value)
        const lines = text.split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const chunk: PullProgress = JSON.parse(raw)
            setPullProgress(prev => ({ ...prev, [modelId]: chunk }))
            if (chunk.status === 'done') {
              await refresh()
              return
            }
          } catch { /* malformed */ }
        }
        readChunk()
      }
      readChunk()
    }).catch(err => {
      setPullProgress(prev => ({ ...prev, [modelId]: { status: 'error', error: String(err) } }))
    })

    setPullProgress(prev => ({ ...prev, [modelId]: { status: 'pulling' } }))
  }, [refresh])

  const deleteModel = useCallback(async (modelId: string) => {
    await fetch(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' })
    await refresh()
  }, [refresh])

  const activateModel = useCallback(async (modelId: string) => {
    await fetch('/api/models/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId, provider: 'ollama' }),
    })
    setActiveModel(modelId)
  }, [])

  return { models, activeModel, loading, pullProgress, refresh, pullModel, deleteModel, activateModel }
}
