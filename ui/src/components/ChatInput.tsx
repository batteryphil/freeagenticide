import { useState, useRef, useCallback, type KeyboardEvent } from 'react'

interface Props {
  onSend: (text: string) => void
  onInterrupt: () => void
  streaming: boolean
  connected: boolean
}

export function ChatInput({ onSend, onInterrupt, streaming, connected }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 140) + 'px'
  }, [])

  const handleSend = useCallback(() => {
    const msg = value.trim()
    if (!msg || !connected || streaming) return
    onSend(msg)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, connected, streaming, onSend])

  const handleKey = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  return (
    <div className="chat-input-area">
      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          id="chat-input"
          className="chat-input"
          value={value}
          onChange={e => { setValue(e.target.value); autoResize() }}
          onKeyDown={handleKey}
          placeholder={connected ? 'Message Antigravity… (Shift+Enter for newline)' : 'Connecting…'}
          disabled={!connected}
          rows={1}
          aria-label="Chat input"
        />
        {streaming ? (
          <button
            id="btn-stop"
            className="btn-stop"
            onClick={onInterrupt}
            title="Stop generation"
            aria-label="Stop"
          >
            ■ Stop
          </button>
        ) : (
          <button
            id="btn-send"
            className="btn-send"
            onClick={handleSend}
            disabled={!connected || !value.trim()}
            title="Send (Enter)"
            aria-label="Send"
          >
            ↑ Send
          </button>
        )}
      </div>
      <div className="chat-hint">
        {connected ? 'Enter to send · Shift+Enter for newline' : '⏳ Reconnecting to backend…'}
      </div>
    </div>
  )
}
