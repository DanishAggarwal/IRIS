import React, { useState, useRef, useEffect } from 'react'
import { Send, CornerDownLeft, AlertCircle } from 'lucide-react'

interface MessageComposerProps {
  onSendMessage: (query: string) => void
  isLoading: boolean
  disabled?: boolean
  maxLength?: number
}

export const MessageComposer: React.FC<MessageComposerProps> = ({
  onSendMessage,
  isLoading,
  disabled = false,
  maxLength = 1000,
}) => {
  const [text, setText] = useState<string>('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const charCount = text.length
  const isOverLimit = charCount > maxLength
  const isNearLimit = charCount > maxLength * 0.9
  const isEmptyOrWhitespace = text.trim().length === 0
  const canSubmit = !isEmptyOrWhitespace && !isOverLimit && !isLoading && !disabled

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 180)}px`
    }
  }, [text])

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault()
    }
    if (canSubmit) {
      onSendMessage(text)
      setText('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="iris-composer-form">
      <div className={`iris-composer-box ${isOverLimit ? 'iris-composer-error' : ''}`}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about PEC courses, syllabus, or academic regulations..."
          disabled={isLoading || disabled}
          rows={1}
          className="iris-composer-textarea"
          aria-label="Student question input"
          maxLength={maxLength + 100} // allow slight typing past limit so user sees overflow feedback
        />

        <div className="iris-composer-toolbar">
          <div className="iris-composer-left">
            <span className="iris-composer-shortcut">
              <CornerDownLeft size={12} className="inline mr-1" />
              <span>Press Enter to send, Shift+Enter for newline</span>
            </span>

            {isOverLimit && (
              <span className="iris-limit-warning" role="alert">
                <AlertCircle size={13} />
                <span>Exceeds {maxLength} character limit</span>
              </span>
            )}
          </div>

          <div className="iris-composer-right">
            <span
              className={`iris-char-counter ${
                isOverLimit ? 'text-rose-600 font-semibold' : isNearLimit ? 'text-amber-600' : ''
              }`}
            >
              {charCount} / {maxLength}
            </span>

            <button
              type="submit"
              disabled={!canSubmit}
              className="iris-btn-send"
              aria-label="Send question"
              title={
                isLoading
                  ? 'IRIS is processing...'
                  : isOverLimit
                  ? `Question must be under ${maxLength} characters`
                  : isEmptyOrWhitespace
                  ? 'Type a question to send'
                  : 'Send question (Enter)'
              }
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </div>
    </form>
  )
}
