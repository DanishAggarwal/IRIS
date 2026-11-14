import React, { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react'
import { CitationItem } from './CitationItem'
import type { Citation } from '../../types/api'

interface CitationListProps {
  citations: Citation[]
}

export const CitationList: React.FC<CitationListProps> = ({ citations }) => {
  const [isSectionOpen, setIsSectionOpen] = useState<boolean>(true)

  if (!citations || citations.length === 0) {
    return null
  }

  return (
    <div className="iris-citations-container">
      <button
        type="button"
        onClick={() => setIsSectionOpen(!isSectionOpen)}
        className="iris-citations-toggle-bar"
        aria-expanded={isSectionOpen}
      >
        <div className="iris-citations-badge">
          <BookOpen size={14} className="iris-citations-badge-icon" />
          <span>
            Institutional Sources ({citations.length})
          </span>
        </div>
        <div className="iris-citations-toggle-icon">
          {isSectionOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {isSectionOpen && (
        <div className="iris-citations-list" role="list">
          {citations.map((citation, idx) => (
            <CitationItem
              key={`${citation.document}-${citation.pages.join('-')}-${idx}`}
              citation={citation}
              index={idx}
            />
          ))}
        </div>
      )}
    </div>
  )
}
