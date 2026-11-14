import React, { useState } from 'react'
import { FileText, ChevronDown, ChevronUp, CheckCircle2 } from 'lucide-react'
import type { Citation } from '../../types/api'

interface CitationItemProps {
  citation: Citation
  index: number
}

function formatPageNumbers(pages: number[]): string {
  if (!pages || pages.length === 0) {
    return 'Page unknown'
  }
  const sorted = [...pages].sort((a, b) => a - b)
  if (sorted.length === 1) {
    return `Page ${sorted[0]}`
  }
  if (sorted.length === 2 && sorted[1] === sorted[0] + 1) {
    return `Pages ${sorted[0]}–${sorted[1]}`
  }
  return `Pages ${sorted.join(', ')}`
}

export const CitationItem: React.FC<CitationItemProps> = ({ citation, index }) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false)
  const pageLabel = formatPageNumbers(citation.pages)

  const hasExtraDetails = Boolean(
    citation.section_title || citation.claim || citation.page_spans?.length,
  )

  return (
    <div className="iris-citation-item">
      <div className="iris-citation-main">
        <div className="iris-citation-header">
          <FileText size={15} className="iris-citation-icon" aria-hidden="true" />
          <div className="iris-citation-title-group">
            <span className="iris-citation-filename" title={citation.document}>
              {citation.document}
            </span>
            <span className="iris-citation-pages">{pageLabel}</span>
          </div>
        </div>

        {hasExtraDetails && (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="iris-citation-toggle"
            aria-expanded={isExpanded}
            aria-label={`Toggle citation ${index + 1} details`}
          >
            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        )}
      </div>

      {citation.section_title && (
        <div className="iris-citation-section">
          <span className="iris-citation-section-label">Section:</span>{' '}
          <span className="iris-citation-section-text">{citation.section_title}</span>
        </div>
      )}

      {isExpanded && (
        <div className="iris-citation-details">
          {citation.claim && (
            <div className="iris-citation-claim">
              <span className="iris-citation-detail-label">Supported Claim:</span>
              <p className="iris-citation-claim-text">{citation.claim}</p>
            </div>
          )}
          {citation.claim_supported && (
            <div className="iris-citation-grounded-badge">
              <CheckCircle2 size={12} className="text-emerald-600" />
              <span>Verified against institutional text</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
