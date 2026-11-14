import React from 'react'
import Markdown from 'react-markdown'
import { AlertCircle } from 'lucide-react'
import { CitationList } from '../Citation/CitationList'
import type { Citation } from '../../types/api'

interface AnsweredCardProps {
  content: string
  citations?: Citation[]
  limitations?: string | null
}

export const AnsweredCard: React.FC<AnsweredCardProps> = ({
  content,
  citations = [],
  limitations,
}) => {
  return (
    <div className="iris-card iris-answered-card">
      <div className="iris-markdown-prose">
        <Markdown>{content}</Markdown>
      </div>

      {limitations && (
        <div className="iris-limitations-box">
          <AlertCircle size={15} className="iris-limitations-icon" />
          <span className="iris-limitations-text">{limitations}</span>
        </div>
      )}

      {citations.length > 0 && <CitationList citations={citations} />}
    </div>
  )
}
