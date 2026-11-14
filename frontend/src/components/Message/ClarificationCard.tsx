import React from 'react'
import Markdown from 'react-markdown'
import { HelpCircle, CornerDownLeft } from 'lucide-react'

interface ClarificationCardProps {
  content: string
  clarificationQuestion?: string | null
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  content,
  clarificationQuestion,
}) => {
  return (
    <div className="iris-card iris-clarification-card">
      <div className="iris-card-banner iris-banner-amber">
        <HelpCircle size={17} className="iris-card-banner-icon text-amber-600" />
        <span className="iris-card-banner-title">Clarification Needed</span>
      </div>

      <div className="iris-clarification-body">
        {clarificationQuestion ? (
          <div className="iris-clarification-highlight">
            <p className="iris-clarification-question-text">{clarificationQuestion}</p>
          </div>
        ) : null}

        {content && content !== clarificationQuestion && (
          <div className="iris-markdown-prose iris-clarification-prose">
            <Markdown>{content}</Markdown>
          </div>
        )}

        <div className="iris-clarification-hint">
          <CornerDownLeft size={14} className="iris-hint-icon" />
          <span>Please enter your clarification in the message box below to continue.</span>
        </div>
      </div>
    </div>
  )
}
