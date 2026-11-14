import React from 'react'
import { BookOpen, GraduationCap, FileCheck, ArrowRight, Sparkles } from 'lucide-react'

interface WelcomeScreenProps {
  onSelectQuestion: (question: string) => void
  disabled?: boolean
}

interface SuggestedPrompt {
  id: string
  title: string
  category: string
  icon: React.ReactNode
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  onSelectQuestion,
  disabled = false,
}) => {
  const suggestions: SuggestedPrompt[] = [
    {
      id: 'cloud-obj',
      title: 'What are the course objectives of Cloud Computing?',
      category: 'Course Syllabus',
      icon: <BookOpen size={16} className="text-blue-600" />,
    },
    {
      id: 'dl-eval',
      title: 'What are the evaluation components of Deep Learning?',
      category: 'Course Handout',
      icon: <GraduationCap size={16} className="text-indigo-600" />,
    },
    {
      id: 'senate-att',
      title: 'What are the attendance rules mentioned in the Senate regulations?',
      category: 'Senate Regulations',
      icon: <FileCheck size={16} className="text-emerald-600" />,
    },
    {
      id: 'dl-labs',
      title: 'What are the laboratory experiments for Deep Learning?',
      category: 'Practical Curriculum',
      icon: <Sparkles size={16} className="text-purple-600" />,
    },
  ]

  return (
    <div className="iris-welcome-screen">
      <div className="iris-welcome-hero">
        <div className="iris-welcome-badge">
          <Sparkles size={15} />
          <span>Grounded Institutional Assistant</span>
        </div>
        <h2 className="iris-welcome-title">Hello! I'm IRIS.</h2>
        <p className="iris-welcome-description">
          Ask me about academic rules, course objectives, examinations, attendance criteria, and
          departmental procedures. Every answer is grounded with exact document and page citations.
        </p>
      </div>

      <div className="iris-suggestions-container">
        <h3 className="iris-suggestions-heading">Suggested questions from the PEC corpus</h3>
        <div className="iris-suggestions-grid">
          {suggestions.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelectQuestion(item.title)}
              className="iris-suggestion-card"
            >
              <div className="iris-suggestion-top">
                <span className="iris-suggestion-icon">{item.icon}</span>
                <span className="iris-suggestion-category">{item.category}</span>
              </div>
              <p className="iris-suggestion-title">{item.title}</p>
              <div className="iris-suggestion-footer">
                <span className="iris-suggestion-action">Ask this question</span>
                <ArrowRight size={13} className="iris-suggestion-arrow" />
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
