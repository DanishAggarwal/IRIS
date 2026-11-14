import React from 'react'
import Markdown from 'react-markdown'
import { Building2, Info, CheckCircle2 } from 'lucide-react'
import { CitationList } from '../Citation/CitationList'
import type { Citation } from '../../types/api'

interface HandoffCardProps {
  content: string
  handoffRecommendation?: string | null
  citations?: Citation[]
}

export const HandoffCard: React.FC<HandoffCardProps> = ({
  content,
  handoffRecommendation,
  citations = [],
}) => {
  return (
    <div className="iris-card iris-handoff-card">
      <div className="iris-card-banner iris-banner-indigo">
        <Info size={17} className="iris-card-banner-icon text-indigo-600" />
        <span className="iris-card-banner-title">Administrative Handoff</span>
      </div>

      <div className="iris-handoff-body">
        <div className="iris-markdown-prose iris-handoff-prose">
          <Markdown>{content}</Markdown>
        </div>

        {handoffRecommendation && (
          <div className="iris-recommendation-box">
            <div className="iris-recommendation-header">
              <Building2 size={16} className="iris-recommendation-icon" />
              <span className="iris-recommendation-title">Recommended Authority</span>
            </div>
            <p className="iris-recommendation-text">{handoffRecommendation}</p>
          </div>
        )}

        <div className="iris-handoff-note">
          <CheckCircle2 size={13} className="iris-handoff-note-icon" />
          <span>
            Please verify requirements and deadlines directly with the recommended office. IRIS
            does not create tickets or transmit requests on your behalf.
          </span>
        </div>

        {citations.length > 0 && <CitationList citations={citations} />}
      </div>
    </div>
  )
}
