import { useState, useCallback, useRef } from 'react'

export interface RunEvent {
  type: 'stdout' | 'stderr' | 'system' | 'exit' | 'stream_end'
  data: string
  pid?: number
  code?: number   // exit code
  url?: string    // for HTML output
}

export interface UseRunner {
  output: RunEvent[]
  running: boolean
  pid: number | null
  htmlUrl: string | null
  run: (code: string, language: string) => void
  killProcess: () => void
  clearOutput: () => void
}

/**
 * useRunner — manages a single active run against the /api/run SSE endpoint.
 *
 * Streams events into the output array, tracks the running PID,
 * and surfaces an htmlUrl when the program produces an HTML file.
 */
export function useRunner(): UseRunner {
  const [output, setOutput] = useState<RunEvent[]>([])
  const [running, setRunning] = useState(false)
  const [pid, setPid] = useState<number | null>(null)
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback((code: string, language: string) => {
    // Abort any previous run
    abortRef.current?.abort()
    const abort = new AbortController()
    abortRef.current = abort

    setOutput([])
    setHtmlUrl(null)
    setPid(null)
    setRunning(true)

    fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language, filename: 'main' }),
      signal: abort.signal,
    })
      .then(async resp => {
        const reader = resp.body?.getReader()
        if (!reader) return
        const decoder = new TextDecoder()

        const readChunk = async () => {
          let done = false
          let value: Uint8Array | undefined

          try {
            ;({ done, value } = await reader.read())
          } catch {
            setRunning(false)
            return
          }

          if (done) {
            setRunning(false)
            return
          }

          const text = decoder.decode(value, { stream: true })
          const lines = text.split('\n').filter(l => l.startsWith('data: '))

          for (const line of lines) {
            const raw = line.slice(6).trim()
            if (!raw) continue
            try {
              const event: RunEvent = JSON.parse(raw)

              if (event.type === 'stream_end') {
                setRunning(false)
                return
              }

              if (event.pid && event.pid > 0 && event.type === 'system' && !pid) {
                setPid(event.pid)
              }

              if (event.url) {
                setHtmlUrl(event.url)
              }

              setOutput(prev => [...prev, event])
            } catch { /* malformed */ }
          }

          readChunk()
        }

        readChunk()
      })
      .catch(err => {
        if ((err as Error).name !== 'AbortError') {
          setOutput(prev => [...prev, {
            type: 'system',
            data: `❌ Connection error: ${err}`,
          }])
        }
        setRunning(false)
      })
  }, [pid])

  const killProcess = useCallback(() => {
    abortRef.current?.abort()
    if (pid) {
      fetch('/api/run/kill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid }),
      }).catch(() => {})
    }
    setRunning(false)
    setOutput(prev => [...prev, { type: 'system', data: '⛔ Killed by user.' }])
  }, [pid])

  const clearOutput = useCallback(() => {
    setOutput([])
    setHtmlUrl(null)
    setPid(null)
  }, [])

  return { output, running, pid, htmlUrl, run, killProcess, clearOutput }
}
